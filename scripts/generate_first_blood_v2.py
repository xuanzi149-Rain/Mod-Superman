"""Create a sparse Damage override, preserving the game's active weapon rules."""

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OBJECT = "UND_Duergar_ShortswordOfFirstBlood"
MODULE_UUID = "fa86e11f-65e1-7489-881e-69cb2b80e055"
MODULE = f"FirstBloodDamageTest_{MODULE_UUID}"


def runtime_override(*, confirmed: bool) -> bytes:
    if not confirmed:
        raise ValueError("Confirm the fixed base damage change 1d6 -> 2d6 first.")
    # Same-name inheritance is used by the shipped Honour Weapon overrides.
    # Do not copy DefaultBoosts or PassivesOnEquip from a particular difficulty.
    return (
        f'new entry "{OBJECT}"\r\n'
        'type "Weapon"\r\n'
        f'using "{OBJECT}"\r\n'
        'data "Damage" "2d6"\r\n\r\n'
    ).encode("utf-8")


def metadata() -> bytes:
    tree = ET.parse(ROOT / "build/first-blood/inspection/python-pak/meta.lsx")
    info = tree.find('.//node[@id="ModuleInfo"]')
    fields = {a.get("id"): a for a in info.findall("attribute")}
    if fields["UUID"].get("value") != MODULE_UUID or fields["Folder"].get("value") != MODULE:
        raise ValueError("Unexpected module identity in the validated manifest.")
    fields["Version64"].set("value", "36028797018963971")
    fields["Description"].set("value", "Doubles base damage to 2d6 using a sparse override. Preserves the active game rules for full-health bonus damage.")
    fields["MD5"].set("value", "")
    fields["FileSize"].set("value", "0")
    ET.indent(tree, space="    ")
    return ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True) + b"\n"


def write_output(output: Path, *, confirmed: bool) -> Path:
    runtime = runtime_override(confirmed=confirmed)
    manifest = metadata()
    output.mkdir(parents=True, exist_ok=False)
    weapon = output / "mod-source/Public" / MODULE / "Stats/Generated/Data/Weapon.txt"
    meta = output / "mod-source/Mods" / MODULE / "meta.lsx"
    weapon.parent.mkdir(parents=True, exist_ok=True)
    meta.parent.mkdir(parents=True, exist_ok=True)
    weapon.write_bytes(runtime)
    meta.write_bytes(manifest)
    (output / "generation.json").write_text(json.dumps({
        "template_version": "first-blood-v2", "module_uuid": MODULE_UUID,
        "object": OBJECT, "confirmed_damage": "2d6", "explicit_game_fields": ["Damage"],
        "inheritance": "same-name source record, matching shipped Honour override pattern",
        "pak_creation": "not_performed", "game_regression": "not_performed",
        "toolkit_resave": "not_supported_by_this_workflow",
    }, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/first-blood/v2")
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
