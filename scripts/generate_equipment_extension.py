"""Generate three confirmed, separate First Blood equipment test modules."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OBJECT = "UND_Duergar_ShortswordOfFirstBlood"
OLD_PASSIVE = "UND_Duergar_ShortswordOfFirstBlood_Passive"
DEX_PASSIVE = "ModSuperman_EquipmentDexterityTest"
NAME_HANDLE = "he122ab64ge979g48b4gb31bg37c62572e3f9"
NAMESPACE = uuid.UUID("fa86e11f-65e1-7489-881e-69cb2b80e055")
KINDS = {"name": "FirstBloodNameTest", "dexterity": "FirstBloodDexterityTest", "alert": "FirstBloodAlertTest"}


def identity(kind: str) -> tuple[str, str]:
    if kind not in KINDS:
        raise ValueError("Only name, dexterity and alert tests are supported.")
    identifier = str(uuid.uuid5(NAMESPACE, KINDS[kind]))
    return f"{KINDS[kind]}_{identifier}", identifier


def localize(entries: list[tuple[str, str, str]]) -> bytes:
    root = ET.Element("contentList")
    for handle, version, value in entries:
        ET.SubElement(root, "content", contentuid=handle, version=version).text = value
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def weapon_override(fields: list[tuple[str, str]]) -> bytes:
    lines = [f'new entry "{OBJECT}"', 'type "Weapon"', f'using "{OBJECT}"']
    lines.extend(f'data "{key}" "{value}"' for key, value in fields)
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def module_meta(kind: str) -> bytes:
    folder, identifier = identity(kind)
    tree = ET.parse(ROOT / "build/first-blood/v2/mod-source/Mods/FirstBloodDamageTest_fa86e11f-65e1-7489-881e-69cb2b80e055/meta.lsx")
    info = tree.find('.//node[@id="ModuleInfo"]')
    descriptions = {
        "name": "Rename Shortsword of First Blood to the confirmed Chinese name. No Stats changes.",
        "dexterity": "Grants Dexterity +2 while equipped, preserving the original full-health effect. Do not enable with FirstBloodAlertTest.",
        "alert": "Replaces the original full-health bonus with Alert. Deliberately removes its Honour conditional boost. Do not enable with FirstBloodDexterityTest.",
    }
    values = {"Name": KINDS[kind], "UUID": identifier, "Folder": folder,
              "Description": descriptions[kind], "MD5": "", "FileSize": "0", "PublishHandle": "0", "Version64": "36028797018963968"}
    for field in info.findall("attribute"):
        if field.get("id") in values:
            field.set("value", values[field.get("id")])
    children = info.find("children")
    if children is not None:
        info.remove(children)
    ET.indent(tree, space="    ")
    return ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True) + b"\n"


def generate_files(kind: str, *, confirmed: bool) -> dict[Path, bytes]:
    if not confirmed:
        raise ValueError("Confirm the fixed name, Dexterity +2 and Alert-replacement parameters first.")
    module, _ = identity(kind)
    root = ET.parse(ROOT / "samples/equipment-extension/source/original-root-node.xml").getroot()
    display = root.find('./attribute[@id="DisplayName"]')
    if display.get("handle") != NAME_HANDLE or display.get("version") != "2":
        raise ValueError("Original name handle/version changed; reverify source.")
    alert = (ROOT / "samples/equipment-extension/source/Alert.txt").read_text(encoding="utf-8-sig")
    if 'data "Boosts" "Initiative(5);StatusImmunity(SURPRISED)"' not in alert:
        raise ValueError("Verified Alert passive has changed.")
    files = {Path("Mods") / module / "meta.lsx": module_meta(kind)}
    if kind == "name":
        content = localize([(NAME_HANDLE, "2", "曙光短剑")])
        files[Path("Mods") / module / "Localization/Chinese/chinese.xml"] = content
        return files
    data = Path("Public") / module / "Stats/Generated/Data"
    if kind == "dexterity":
        files[data / "Weapon.txt"] = weapon_override([("PassivesOnEquip", OLD_PASSIVE + ";" + DEX_PASSIVE)])
        files[data / "Passive.txt"] = (
            f'new entry "{DEX_PASSIVE}"\r\n'
            'type "PassiveData"\r\n'
            'data "DisplayName" "ModSupermanDexterityName;1"\r\n'
            'data "Description" "ModSupermanDexterityDescription;1"\r\n'
            'data "Boosts" "Ability(Dexterity,2)"\r\n\r\n'
        ).encode("utf-8")
        files[Path("Mods") / module / "Localization/Chinese/chinese.xml"] = localize([
            ("ModSupermanDexterityName", "1", "敏捷加成"),
            ("ModSupermanDexterityDescription", "1", "装备这把武器时，敏捷增加 2。"),
        ])
    else:
        # Intentional replacement: Honour uses DefaultBoosts for the original bonus.
        files[data / "Weapon.txt"] = weapon_override([
            ("PassivesOnEquip", "Alert"), ("DefaultBoosts", "WeaponProperty(Magical)"),
        ])
    return files


def write_output(output: Path, *, confirmed: bool) -> Path:
    generated = {kind: generate_files(kind, confirmed=confirmed) for kind in KINDS}
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"date": "2026-10-13", "confirmed_parameters": {
        "name": "曙光短剑", "dexterity": 2, "passive": "replace original full-health bonus with Alert",
    }, "mutually_exclusive": [KINDS["dexterity"], KINDS["alert"]], "modules": {}, "game_verification": "not_performed"}
    for kind, files in generated.items():
        for relative, data in files.items():
            path = output / kind / "mod-source" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        module, identifier = identity(kind)
        manifest["modules"][kind] = {"folder": module, "uuid": identifier,
            "files_sha256": {str(p): hashlib.sha256(data).hexdigest() for p, data in files.items()}}
    (output / "generation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/equipment-extension")
    parser.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()
    try:
        print(f"Generated: {write_output(args.output, confirmed=args.confirmed).resolve()}")
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"Generation stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
