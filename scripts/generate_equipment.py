"""Equipment MVP: catalog-based requests -> sparse Stats/localization -> verified PAK."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

try:
    from .equipment_catalog import CATALOG_PATH, load_catalog
    from .generate_mod import ROOT, DIVINE, ValidationError, localization, no_duplicate_keys, run_tool
except ImportError:
    from equipment_catalog import CATALOG_PATH, load_catalog
    from generate_mod import ROOT, DIVINE, ValidationError, localization, no_duplicate_keys, run_tool

FIELDS = {"damage": "Damage", "versatile_damage": "VersatileDamage", "weight_kg": "Weight", "rarity": "Rarity"}
RARITIES = ("Common", "Uncommon", "Rare", "VeryRare", "Legendary")
FIRST_BLOOD = "equipment:1e172d76-3433-4ee7-ae1a-9e7d8ae0f12b"
RULES = {
    "damage": {"type": "dice_string", "count": [1, 10], "sides": [4, 6, 8, 10, 12, 20]},
    "versatile_damage": {"type": "dice_string", "count": [1, 10], "sides": [4, 6, 8, 10, 12, 20]},
    "name": {"type": "string", "length": [1, 60], "language": "Chinese"},
    "weight_kg": {"type": "number", "range": [0, 100], "decimal_places": 3},
    "rarity": {"type": "enum", "values": list(RARITIES)},
}


def validate_request(request, *, catalog=None, allow_unverified=False):
    catalog = load_catalog() if catalog is None else catalog
    if not isinstance(request, dict) or set(request) != {"object", "changes"}:
        raise ValidationError("Request must contain exactly object and changes.")
    key = request["object"]
    if not isinstance(key, str) or key not in catalog["items"]:
        raise ValidationError("Unknown equipment ID; select an ID from --list.")
    item = catalog["items"][key]
    changes = request["changes"]
    if not isinstance(changes, dict) or not changes:
        raise ValidationError("Changes must be a nonempty object.")
    clean, warnings = {}, []
    for field, value in changes.items():
        if field not in RULES or field not in item["capabilities"]:
            raise ValidationError(f"Unsupported field {field}: {item['blocked_fields'].get(field, 'not available')}")
        if field in ("damage", "versatile_damage"):
            if not isinstance(value, str) or not re.fullmatch(r"(?:[1-9]|10)d(?:4|6|8|10|12|20)", value):
                raise ValidationError("Dice must be NdS, count 1..10, sides 4/6/8/10/12/20.")
        elif field == "name":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 60 or any(
                ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF) for c in value
            ):
                raise ValidationError("Name must be 1..60 characters without control characters.")
            value = value.strip()
        elif field == "weight_kg":
            if type(value) not in (int, float):
                raise ValidationError("Weight must be a JSON number in kg.")
            decimal = Decimal(str(value))
            if not decimal.is_finite() or not 0 <= decimal <= 100 or decimal != decimal.quantize(Decimal('0.001')):
                raise ValidationError("Weight must be 0..100 kg, at most three decimals.")
            value = float(decimal) if decimal != decimal.to_integral() else int(decimal)
        elif field == "rarity":
            if not isinstance(value, str) or value not in RARITIES:
                raise ValidationError("Rarity must be Common/Uncommon/Rare/VeryRare/Legendary.")
        clean[field] = value
        known = key == FIRST_BLOOD and ((field == "damage" and value == "2d6") or (field == "name" and value == "曙光短剑"))
        if not known:
            warnings.append(f"{field}={value!r}: no recorded game test for this object/value.")
    if len(clean) > 1:
        warnings.append("This combination requires a separate game regression test.")
    if warnings and not allow_unverified:
        raise ValidationError("Use --experimental for unverified requests: " + " ".join(warnings))
    return {"object": key, "changes": clean}, warnings


def render_files(request, module_id, *, catalog=None):
    catalog = load_catalog() if catalog is None else catalog
    request, _ = validate_request(request, catalog=catalog, allow_unverified=True)
    item = catalog["items"][request["object"]]
    identifier = str(uuid.UUID(module_id))
    module = "ModSuperman_" + identifier
    tree = ET.parse(ROOT / "templates/module.lsx")
    info = tree.find('.//node[@id="ModuleInfo"]')
    metadata = {"UUID": identifier, "Folder": module, "Name": f"ModSuperman {item['display_name']} {identifier[:8]}",
                "Description": json.dumps(request["changes"], ensure_ascii=False), "Version64": "36028797018963968",
                "MD5": "", "FileSize": "0", "PublishHandle": "0"}
    for attr in info.findall("attribute"):
        if attr.get("id") in metadata:
            attr.set("value", metadata[attr.get("id")])
    for children in info.findall("children"):
        info.remove(children)
    ET.indent(tree, space="    ")
    files = {Path("Mods") / module / "meta.lsx": ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True) + b"\n"}
    changes = request["changes"]
    fields = [(FIELDS[k], v) for k, v in changes.items() if k in FIELDS]
    if fields:
        record, kind = item["record"], item["stats_type"]
        # Only trusted catalog identifiers are used in Stats syntax.
        if kind not in ("Weapon", "Armor") or not re.fullmatch(r"[A-Za-z0-9_]+", record):
            raise ValidationError("Catalog contains an invalid Stats identifier/type.")
        lines = [f'new entry "{record}"', f'type "{kind}"', f'using "{record}"']
        for field, value in fields:
            text = format(Decimal(str(value)), 'f') if field == "Weight" else str(value)
            lines.append(f'data "{field}" "{text}"')
        files[Path("Public") / module / "Stats/Generated/Data" / (kind + ".txt")] = ("\n".join(lines) + "\n").encode("utf-8")
    if "name" in changes:
        files[Path("Mods") / module / "Localization/Chinese/chinese.xml"] = localization(
            [(item["name_handle"], item["name_version"], changes["name"])])
    return files


def generate(request, output_root=ROOT / "build/equipment-mvp", *, confirmed=False, allow_unverified=False, packager=DIVINE, catalog_path=CATALOG_PATH):
    if confirmed is not True:
        raise ValidationError("Confirm the selected object and parameters before generation (--confirmed).")
    catalog = load_catalog(catalog_path)
    clean, warnings = validate_request(request, catalog=catalog, allow_unverified=allow_unverified)
    if not packager.is_file():
        raise FileNotFoundError("LSLib Divine.exe is missing; specify --packager.")
    identifier = str(uuid.uuid4())
    files = render_files(clean, identifier, catalog=catalog)
    item = catalog["items"][clean["object"]]
    directory = output_root.resolve() / identifier
    directory.mkdir(parents=True, exist_ok=False)
    source = directory / "mod-source"
    for relative, data in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    pak = directory / ("ModSuperman_" + identifier + ".pak")
    result = {"request": clean, "module_uuid": identifier, "catalog_version": catalog["catalog_version"],
              "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
              "record": item["record"], "original": item["original"], "honour_original": item["honour_original"],
              "shared_record_templates": item["shared_record_templates"], "name_reference_templates": item["name_reference_templates"],
              "potential_descendant_records": item["descendant_records"],
              "scope": item["scope"], "experimental": bool(warnings), "warnings": warnings,
              "source_generation": "passed", "pak_creation": "pending", "package_check": "pending", "game_validation": "not_performed", "install": "not_performed"}
    try:
        run_tool(packager, "-a", "create-package", "-s", str(source), "-d", str(pak))
        if not pak.is_file() or not pak.stat().st_size:
            raise RuntimeError("No nonempty PAK was generated.")
        result["pak_creation"] = "passed"
        unpacked = directory / "unpacked-check"
        run_tool(packager, "-a", "extract-package", "-s", str(pak), "-d", str(unpacked))
        observed = {p.relative_to(unpacked): p.read_bytes() for p in unpacked.rglob("*") if p.is_file()}
        if observed != files:
            raise RuntimeError("PAK contents differ from generated files.")
        result.update(package_check="passed", pak_sha256=hashlib.sha256(pak.read_bytes()).hexdigest(), pak_filename=pak.name)
    except Exception as exc:
        result.update(error=str(exc), package_check="failed")
        raise
    finally:
        (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "使用说明.txt").write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) +
        "\n退出游戏，将 .pak 复制到 %LOCALAPPDATA%\\Larian Studios\\Baldur's Gate 3\\Mods，重启并启用。\n"
        "停用同对象的旧测试包，加载测试存档，重新装备后检查；恢复时停用并重启加载原档。\n"
        "Stats 修改影响共用记录的装备，可能被子记录继承；名称只覆盖简体中文。\n"
        "伤害与双手伤害分别修改，未提交的字段保持原规则。未直接修改售价，最终价格需游戏实测。\n"
        "已通过生成和解包检查，本次游戏验证待完成。\n" + "\n".join(warnings), encoding="utf-8")
    return pak


def main():
    # Keep Chinese output readable when PowerShell/tooling captures the process.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--search", default="")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--rules", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "build/equipment-mvp")
    parser.add_argument("--packager", type=Path, default=DIVINE)
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--experimental", action="store_true")
    args = parser.parse_args()
    try:
        if args.rules:
            print(json.dumps(RULES, ensure_ascii=False, indent=2))
        elif args.list:
            items = load_catalog(args.catalog)["items"].values()
            selected = [i for i in items if (not args.category or i["category"] == args.category) and
                        args.search.casefold() in (i["display_name"] + " " + i["record"] + " " + i["object_id"]).casefold()]
            print(json.dumps({"matches": len(selected), "items": selected[:max(0, args.limit)]}, ensure_ascii=False, indent=2))
        else:
            if args.request is None:
                parser.error("--request, --list or --rules is required")
            request = json.loads(args.request.read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicate_keys)
            print(generate(request, args.output_root, confirmed=args.confirmed, allow_unverified=args.experimental,
                           packager=args.packager, catalog_path=args.catalog))
    except (OSError, ValueError, RuntimeError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(f"Generation stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
