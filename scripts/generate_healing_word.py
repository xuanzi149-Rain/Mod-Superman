"""Generate the fixed, locally verified Healing Word 18m -> 36m source files."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MODULE_UUID = "9fd6363d-2acf-4acc-94fa-ae9fee76a604"
MODULE = f"HealingWordRangeTest_{MODULE_UUID}"
OBJECT = "Target_HealingWord"
EDITOR = Path("editor-stats/SpellData/Target.stats")
RUNTIME = Path("runtime-stats/Generated/Data/Spell_Target.txt")
ORIGINAL_RADIUS = 18
TARGET_RADIUS = ORIGINAL_RADIUS * 2
HASHES = {
    EDITOR: "354ec65be4ae157976d17f56944a2d279944a8ab3e4921675df2059f7f1f28f4",
    RUNTIME: "94b4961aef0c13d9ce2133e63791879970c30d5512d0ddbe534ea128fe705a5b",
}


def generate_files(template: Path, *, confirmed: bool) -> dict[Path, bytes]:
    if not confirmed:
        raise ValueError("Confirm Healing Word casting distance 18m -> 36m first.")
    source = {relative: (template / relative).read_bytes() for relative in HASHES}
    for relative, expected in HASHES.items():
        if hashlib.sha256(source[relative]).hexdigest() != expected:
            raise ValueError(f"Verified baseline changed: {relative}")
    text = source[RUNTIME].decode("utf-8-sig")
    if re.findall(r'^new entry "([^"]+)"', text, re.MULTILINE) != [OBJECT]:
        raise ValueError("Expected exactly one Target_HealingWord record.")
    objects = ET.fromstring(source[EDITOR]).findall("./stat_objects/stat_object")
    if len(objects) != 1 or objects[0].find('./fields/field[@name="Name"]').get("value") != "HealingWord":
        raise ValueError("Editor template is not the expected base HealingWord record.")
    anchor = b'data "TargetRadius" "18"'
    pattern = rb'(<field name="TargetRadius"[^>]*value=")18(")'
    if source[RUNTIME].count(anchor) != 1 or len(re.findall(pattern, source[EDITOR])) != 1:
        raise ValueError("TargetRadius must be present once with original value 18.")
    editor = re.sub(pattern, lambda match: match[1] + str(TARGET_RADIUS).encode() + match[2], source[EDITOR], count=1)
    runtime = source[RUNTIME].replace(anchor, b'data "TargetRadius" "36"', 1)
    # These reverse comparisons verify that no other field or byte changed.
    if runtime.replace(b'data "TargetRadius" "36"', anchor, 1) != source[RUNTIME]:
        raise ValueError("Unexpected runtime changes.")
    emitted = ET.fromstring(editor)
    field = emitted.find('./stat_objects/stat_object/fields/field[@name="TargetRadius"]')
    if field.get("value") != str(TARGET_RADIUS):
        raise ValueError("Invalid emitted editor radius.")
    return {EDITOR: editor, RUNTIME: runtime}


def module_metadata() -> bytes:
    """Reuse the locally validated module manifest structure, with a new identity."""
    tree = ET.parse(ROOT / "build/first-blood/inspection/manual/meta.lsx")
    info = tree.find('.//node[@id="ModuleInfo"]')
    values = {
        "Name": "HealingWordRangeTest", "Folder": MODULE, "UUID": MODULE_UUID,
        "Description": "Doubles Healing Word casting distance from 18m to 36m. Upcasts inherit the distance. Healing and resource costs are unchanged.",
        "Version64": "36028797018963968", "MD5": "", "FileSize": "0", "PublishHandle": "0",
    }
    for attribute in info.findall("attribute"):
        if attribute.get("id") in values:
            attribute.set("value", values[attribute.get("id")])
    # No unrelated module scripts or online publish metadata belong in this sample.
    children = info.find("children")
    if children is not None:
        info.remove(children)
    ET.indent(tree, space="    ")
    return ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True) + b"\n"


def write_output(template: Path, output: Path, *, confirmed: bool) -> Path:
    generated = generate_files(template, confirmed=confirmed)
    metadata = module_metadata()
    output.mkdir(parents=True, exist_ok=False)
    for relative, content in generated.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    mod_source = output / "mod-source"
    runtime_target = mod_source / "Public" / MODULE / "Stats/Generated/Data/Spell_Target.txt"
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.write_bytes(generated[RUNTIME])
    meta_target = mod_source / "Mods" / MODULE / "meta.lsx"
    meta_target.parent.mkdir(parents=True, exist_ok=True)
    meta_target.write_bytes(metadata)
    manifest = {
        "template_version": "healing-word-v1", "record": OBJECT,
        "module_uuid": MODULE_UUID, "module_folder": MODULE,
        "confirmed_parameters": {"field": "TargetRadius", "original": ORIGINAL_RADIUS, "new": TARGET_RADIUS, "unit": "m"},
        "template_sha256": {str(p): h for p, h in HASHES.items()},
        "output_sha256": {str(p): hashlib.sha256(data).hexdigest() for p, data in generated.items()},
        "expected_inherited_upcasts": [f"Target_HealingWord_{n}" for n in range(2, 7)],
        "file_generation": "passed", "game_verification": "not_performed",
        "packaging": "not_performed", "toolkit_project_import": "not_performed",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=ROOT / "samples/healing-word/before")
    parser.add_argument("--output", type=Path, default=ROOT / "build/healing-word/generated")
    parser.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()
    try:
        output = write_output(args.template, args.output, confirmed=args.confirmed)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"Generation stopped: {exc}", file=sys.stderr)
        return 1
    print(f"Generated: {output.resolve()}\nActual game distance testing remains required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
