"""Validate a supported JSON request and build a local BG3 PAK without an AI API."""

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIVINE = ROOT / ".tools/lslib/v1.20.4/Packed/Tools/Divine.exe"
WEAPON = "UND_Duergar_ShortswordOfFirstBlood"
OLD_PASSIVE = "UND_Duergar_ShortswordOfFirstBlood_Passive"
NAME_HANDLE = "he122ab64ge979g48b4gb31bg37c62572e3f9"
SPELL_SOURCE = ROOT / "samples/healing-word/before/runtime-stats/Generated/Data/Spell_Target.txt"
SPELL_HASH = "94b4961aef0c13d9ce2133e63791879970c30d5512d0ddbe534ea128fe705a5b"
CATALOG = {
    "first_blood_shortsword": {
        "display_name": "第一滴血短剑", "record": WEAPON,
        "fields": {
            "damage": {"type": "dice_string", "dice_count": [1, 10], "dice_sides": [4, 6, 8, 10, 12, 20], "game_tested": ["2d6"]},
            "dexterity_bonus": {"type": "integer", "range": [1, 4], "game_tested": [2]},
            "name": {"type": "string", "length": [1, 60], "language": "Chinese", "game_tested": ["曙光短剑"]},
            "passive_mode": {"type": "enum", "values": ["keep", "replace_with_alert"], "game_tested": ["keep", "replace_with_alert"]},
        },
    },
    "healing_word": {
        "display_name": "治愈真言", "record": "Target_HealingWord",
        "fields": {"cast_distance_m": {"type": "number", "range": [1, 60], "decimal_places": 1, "game_tested": [36]}},
    },
}


class ValidationError(ValueError):
    pass


def validate_request(request: dict, *, allow_unverified: bool = False) -> tuple[dict, list[str]]:
    if not isinstance(request, dict) or set(request) != {"object", "changes"}:
        raise ValidationError("Request must contain exactly object and changes.")
    object_id = request["object"]
    if not isinstance(object_id, str) or object_id not in CATALOG:
        raise ValidationError("Unsupported object.")
    changes = request["changes"]
    allowed = CATALOG[object_id]["fields"]
    if not isinstance(changes, dict) or not changes or any(key not in allowed for key in changes):
        raise ValidationError("Changes must be nonempty and contain only supported fields.")
    clean = {}
    warnings = []
    for key, value in changes.items():
        rule = allowed[key]
        if key == "damage":
            if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]?d(?:4|6|8|10|12|20)", value):
                raise ValidationError("Damage must be NdS, such as 3d6; fixed bonuses and code are unsupported.")
            count, _ = map(int, value.split("d"))
            if count > 10:
                raise ValidationError("Damage dice count must be 1..10.")
        elif key == "dexterity_bonus":
            if type(value) is not int or not 1 <= value <= 4:
                raise ValidationError("Dexterity bonus must be an integer 1..4.")
        elif key == "name":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 60 or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF) for c in value):
                raise ValidationError("Name must contain 1..60 characters, without control characters.")
            value = value.strip()
        elif key == "passive_mode":
            if not isinstance(value, str) or value not in rule["values"]:
                raise ValidationError("Passive mode must be keep or replace_with_alert.")
        elif key == "cast_distance_m":
            if type(value) not in (int, float):
                raise ValidationError("Distance must be a JSON number in meters.")
            try:
                decimal = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValidationError("Invalid distance.") from exc
            if not decimal.is_finite() or not 1 <= decimal <= 60 or decimal != decimal.quantize(Decimal("0.1")):
                raise ValidationError("Distance must be 1..60 meters with at most one decimal place.")
            value = float(decimal) if decimal != decimal.to_integral() else int(decimal)
        clean[key] = value
        if value not in rule["game_tested"]:
            warnings.append(f"{key}={value!r} has no recorded game test.")
    # Combining several Stats behaviors is a new regression case even if each value passed alone.
    gameplay = set(clean) - {"name"}
    if len(gameplay) > 1:
        warnings.append("This combined gameplay modification has not been separately game-tested.")
    if warnings and not allow_unverified:
        raise ValidationError("Use --experimental for unverified values/combinations: " + " ".join(warnings))
    return {"object": object_id, "changes": clean}, warnings


def localization(entries: list[tuple[str, str, str]]) -> bytes:
    root = ET.Element("contentList")
    for handle, version, text in entries:
        ET.SubElement(root, "content", contentuid=handle, version=version).text = text
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def render_files(request: dict, module_id: str) -> dict[Path, bytes]:
    """Accept only a previously validated request; repeat structural validation for library callers."""
    request, _ = validate_request(request, allow_unverified=True)
    identifier = str(uuid.UUID(module_id))
    module = "ModSuperman_" + identifier
    changes = request["changes"]
    tree = ET.parse(ROOT / "templates/module.lsx")
    info = tree.find('.//node[@id="ModuleInfo"]')
    values = {"UUID": identifier, "Folder": module,
        "Name": f"ModSuperman {CATALOG[request['object']]['display_name']} {identifier[:8]}",
        "Description": json.dumps(changes, ensure_ascii=False), "Version64": "36028797018963968",
        "MD5": "", "FileSize": "0", "PublishHandle": "0"}
    for field in info.findall("attribute"):
        if field.get("id") in values:
            field.set("value", values[field.get("id")])
    children = info.find("children")
    if children is not None:
        info.remove(children)
    ET.indent(tree, space="    ")
    files = {Path("Mods") / module / "meta.lsx": ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True) + b"\n"}
    public = Path("Public") / module / "Stats/Generated/Data"
    texts = []
    if request["object"] == "healing_word":
        baseline = SPELL_SOURCE.read_bytes()
        if hashlib.sha256(baseline).hexdigest() != SPELL_HASH:
            raise ValidationError("Healing Word baseline changed; reverify source.")
        value = format(Decimal(str(changes["cast_distance_m"])), "f").rstrip("0").rstrip(".") if isinstance(changes["cast_distance_m"], float) else str(changes["cast_distance_m"])
        files[public / "Spell_Target.txt"] = baseline.replace(b'data "TargetRadius" "18"', f'data "TargetRadius" "{value}"'.encode(), 1)
        return files
    fields = []
    if "damage" in changes:
        fields.append(("Damage", changes["damage"]))
    mode = changes.get("passive_mode", "keep")
    if "passive_mode" in changes or "dexterity_bonus" in changes:
        passives = ["Alert" if mode == "replace_with_alert" else OLD_PASSIVE]
        if "dexterity_bonus" in changes:
            passive = "ModSuperman_Dexterity_" + identifier.replace("-", "")
            handle = "ModSupermanDex" + identifier.replace("-", "")
            amount = changes["dexterity_bonus"]
            passives.append(passive)
            files[public / "Passive.txt"] = (
                f'new entry "{passive}"\r\ntype "PassiveData"\r\n'
                f'data "DisplayName" "{handle};1"\r\n'
                f'data "Description" "{handle}Description;1"\r\n'
                f'data "Boosts" "Ability(Dexterity,{amount})"\r\n\r\n'
            ).encode()
            texts.extend([(handle, "1", f"敏捷 +{amount}"), (handle + "Description", "1", f"装备此武器时敏捷增加 {amount}。")])
        fields.append(("PassivesOnEquip", ";".join(passives)))
        if mode == "replace_with_alert":
            fields.append(("DefaultBoosts", "WeaponProperty(Magical)"))
    if fields:
        lines = [f'new entry "{WEAPON}"', 'type "Weapon"', f'using "{WEAPON}"']
        lines.extend(f'data "{key}" "{value}"' for key, value in fields)
        files[public / "Weapon.txt"] = ("\r\n".join(lines) + "\r\n\r\n").encode()
    if "name" in changes:
        texts.append((NAME_HANDLE, "2", changes["name"]))
    if texts:
        files[Path("Mods") / module / "Localization/Chinese/chinese.xml"] = localization(texts)
    return files


def run_tool(tool: Path, *arguments: str) -> None:
    command = ['dotnet', str(tool.resolve())] if tool.suffix.lower() == '.dll' else [str(tool.resolve())]
    result = subprocess.run([*command, "-g", "bg3", *arguments], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode:
        raise RuntimeError(f"LSLib failed ({result.returncode}): {result.stdout} {result.stderr}")


def generate(request: dict, output_root: Path = ROOT / "build/generated-mods", *, confirmed: bool = False,
             allow_unverified: bool = False, packager: Path = DIVINE) -> Path:
    if confirmed is not True:
        raise ValidationError("Parameters must be explicitly confirmed before generation.")
    clean, warnings = validate_request(request, allow_unverified=allow_unverified)
    if not packager.is_file():
        raise FileNotFoundError("LSLib Divine.exe is missing. See the interface instructions.")
    identifier = str(uuid.uuid4())
    files = render_files(clean, identifier)
    directory = output_root.resolve() / identifier
    directory.mkdir(parents=True, exist_ok=False)
    source = directory / "mod-source"
    for relative, data in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    pak = directory / ("ModSuperman_" + identifier + ".pak")
    result = {"request": clean, "module_uuid": identifier, "catalog_version": "parameterized-v1",
              "experimental": bool(warnings), "warnings": warnings,
              "source_generation": "passed", "pak_creation": "pending", "package_check": "pending",
              "game_validation": "not_performed", "install": "not_performed"}
    manifest = directory / "result.json"
    try:
        run_tool(packager, "-a", "create-package", "-s", str(source), "-d", str(pak))
        if not pak.is_file() or pak.stat().st_size == 0:
            raise RuntimeError("Packager did not produce a nonempty PAK.")
        result["pak_creation"] = "passed"
        unpacked = directory / "unpacked-check"
        run_tool(packager, "-a", "extract-package", "-s", str(pak), "-d", str(unpacked))
        observed = {p.relative_to(unpacked): p.read_bytes() for p in unpacked.rglob("*") if p.is_file()}
        if observed != files:
            raise RuntimeError("PAK content does not match generated source files.")
        result.update(package_check="passed", pak_filename=pak.name, pak_sha256=hashlib.sha256(pak.read_bytes()).hexdigest())
    except Exception as exc:
        result.update(error=str(exc), package_check="failed")
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "使用说明.txt").write_text(
        "本次修改：\n" + json.dumps(clean, ensure_ascii=False, indent=2) +
        "\n安装：退出游戏，将本目录的 .pak 复制到游戏 Mods 目录，重启并在游戏内启用。\n"
        "同一对象的旧测试包或旧生成包请停用，避免覆盖与叠加。重新装备后检查效果。\n"
        "停用：停用本包，完整重启并重新加载原测试档；保留原存档。\n"
        "作用于原记录，不能默认只影响背包的单一实例。名称只覆盖简体中文。\n"
        "治愈真言升环版本可能继承距离；警觉替换会有意移除原满血附伤。\n"
        "本包已完成文件和打包检查，尚未进行本次游戏验证。\n" + "\n".join(warnings), encoding="utf-8")
    return pak


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "build/generated-mods")
    parser.add_argument("--packager", type=Path, default=DIVINE)
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--experimental", action="store_true")
    parser.add_argument("--catalog", action="store_true")
    args = parser.parse_args()
    if args.catalog:
        print(json.dumps(CATALOG, ensure_ascii=False, indent=2))
        return 0
    if args.request is None:
        parser.error("--request is required unless --catalog is used")
    try:
        request = json.loads(args.request.read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicate_keys)
        pak = generate(request, args.output_root, confirmed=args.confirmed,
                       allow_unverified=args.experimental, packager=args.packager)
    except (OSError, ValueError, RuntimeError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(f"Generation stopped: {exc}", file=sys.stderr)
        return 1
    print(f"PAK: {pak}\nGame validation remains pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
