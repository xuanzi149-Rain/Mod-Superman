"""Reproduce the measured FirstBloodDamageTest change using only stdlib."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OBJECT = "UND_Duergar_ShortswordOfFirstBlood"
MODULE = "FirstBloodDamageTest_fa86e11f-65e1-7489-881e-69cb2b80e055"
VERSION = "first-blood-v1"
ORIGINAL_DAMAGE = "1d6"  # Confirmed in Toolkit, inherited from WPN_Shortsword_1.
EDITOR = Path("editor-stats/Stats/Weapon.stats")
RUNTIME = Path("runtime-stats/Generated/Data/Weapon.txt")
HASHES = {
    EDITOR: "56517302ca71b5cc3853fc3665068764501e883da6c53ee8722ccb17498c809b",
    RUNTIME: "de3c17362f7f2835fdb32717515ce399297bf54d2b2571523d98fd757b207089",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_files(template: Path, *, confirmed: bool) -> dict[Path, bytes]:
    """Only support this fixed object and its confirmed 2x base damage request."""
    if not confirmed:
        raise ValueError("Confirm the 1d6 -> 2d6 base damage request before generation.")
    source = {relative: (template / relative).read_bytes() for relative in HASHES}
    runtime = source[RUNTIME].decode("utf-8-sig")
    if re.findall(r'^new entry "([^"]+)"', runtime, re.MULTILINE) != [OBJECT]:
        raise ValueError("Template must contain exactly one entry for the supported object.")
    tree = ET.fromstring(source[EDITOR])
    objects = tree.findall("./stat_objects/stat_object")
    if len(objects) != 1:
        raise ValueError("Editor template must contain exactly one stat object.")
    fields = objects[0].findall("./fields/field")
    names = [field.get("value") for field in fields if field.get("name") == "Name"]
    if names != [OBJECT]:
        raise ValueError("Editor template object does not match the runtime object.")
    if any(field.get("name") == "Damage" for field in fields) or re.search(
        r'^data "Damage"', runtime, re.MULTILINE
    ):
        raise ValueError("Baseline must inherit Damage; explicit Damage is unexpected.")
    for relative, expected in HASHES.items():
        if sha256(source[relative]) != expected:
            raise ValueError(f"Baseline changed: {relative}. Reverify the template first.")

    count, sides = map(int, ORIGINAL_DAMAGE.split("d"))
    damage = f"{count * 2}d{sides}"
    editor_anchor = b"      </fields>"
    runtime_anchor = b'data "ValueUUID" '
    if source[EDITOR].count(editor_anchor) != 1 or source[RUNTIME].count(runtime_anchor) != 1:
        raise ValueError("Unexpected baseline insertion points.")
    result = {
        EDITOR: source[EDITOR].replace(
            editor_anchor,
            f'        <field name="Damage" type="DiceTableFieldDefinition" value="{damage}" />\r\n'.encode()
            + editor_anchor,
            1,
        ),
        RUNTIME: source[RUNTIME].replace(
            runtime_anchor,
            f'data "Damage" "{damage}"\r\n'.encode() + runtime_anchor,
            1,
        ),
    }
    # Parse emitted XML and check that both outputs carry the same intended value.
    generated_fields = ET.fromstring(result[EDITOR]).findall("./stat_objects/stat_object/fields/field")
    if [f.get("value") for f in generated_fields if f.get("name") == "Damage"] != [damage]:
        raise ValueError("Generated editor Damage is invalid.")
    if re.findall(rb'^data "Damage" "([^"]+)"', result[RUNTIME], re.MULTILINE) != [damage.encode()]:
        raise ValueError("Generated runtime Damage is invalid.")
    return result


def write_output(template: Path, output: Path, *, confirmed: bool) -> Path:
    files = generate_files(template, confirmed=confirmed)
    # Never overwrite a baseline, reference sample, or earlier generation.
    output.mkdir(parents=True, exist_ok=False)
    for relative, data in files.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = {
        "template_version": VERSION,
        "object": OBJECT,
        "module_folder": MODULE,
        "confirmed_parameters": {"field": "Damage", "original": ORIGINAL_DAMAGE, "multiplier": 2, "new": "2d6"},
        "original_value_source": "Toolkit screenshots: inherited Damage and Parent value are 1d6",
        "template_sha256": {str(p): h for p, h in HASHES.items()},
        "output_sha256": {str(p): sha256(data) for p, data in files.items()},
        "file_generation": "passed",
        "pak_publication": "not_performed",
        "generated_mod_game_verification": "not_performed",
        "game_version": None,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.txt").write_text(
        "Generated source files, not an installable PAK.\n"
        "Close Toolkit. Copy editor-stats/Stats/Weapon.stats into:\n"
        f"  <game>/Data/Editor/Mods/{MODULE}/Stats/Stats/Weapon.stats\n"
        "Copy runtime-stats/Generated/Data/Weapon.txt into:\n"
        f"  <game>/Data/Public/{MODULE}/Stats/Generated/Data/Weapon.txt\n"
        "Reopen Toolkit and verify Damage=2d6, then save and Publish Local.\n"
        "Keep the manual PAK separately. Replace the installed PAK with the newly published one.\n"
        "Verify the actual game damage formula; other damage sources are not multiplied.\n"
        "Also verify full-health bonus damage, ordinary shortswords and disable/reload recovery.\n"
        "No game version compatibility claim has been established.\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=ROOT / "samples/first-blood/before")
    parser.add_argument("--output", type=Path, default=ROOT / "build/first-blood/python")
    parser.add_argument("--confirmed", action="store_true", help="Confirm the fixed base-damage change 1d6 -> 2d6")
    args = parser.parse_args()
    try:
        path = write_output(args.template, args.output, confirmed=args.confirmed)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"Generation stopped: {exc}", file=sys.stderr)
        return 1
    print(f"Generated: {path.resolve()}\nPAK publication and game verification remain pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
