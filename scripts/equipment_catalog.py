"""Build a versioned equipment catalog from extracted local game data."""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/equipment_catalog.json"
MODULES = [
    ("Shared", "equipment-shared", "equipment-roots-Shared"),
    ("SharedDev", "equipment-shared", "equipment-roots-Shared"),
    ("Gustav", "healing-word-Gustav", "equipment-roots-Gustav"),
    ("GustavDev", "healing-word-Gustav", "equipment-roots-Gustav"),
    ("GustavX", "healing-word-GustavX", "equipment-roots-GustavX"),
]
FIELDS = ("Damage", "VersatileDamage", "Weight", "Rarity")


@dataclass
class Stat:
    name: str
    kind: str
    parent: str | None
    fields: dict
    source: str
    previous: "Stat | None" = None


def parse_stats(text: str, source: str) -> list[Stat]:
    records = []
    for block in re.split(r'(?=^new entry ")', text, flags=re.MULTILINE):
        name = re.match(r'new entry "([^"]+)"', block)
        kind = re.search(r'^type "([^"]+)"', block, re.MULTILINE)
        if not name or not kind:
            continue
        parent = re.search(r'^using "([^"]+)"', block, re.MULTILINE)
        fields = dict(re.findall(r'^data "([^"]+)" "([^"\r\n]*)"', block, re.MULTILINE))
        records.append(Stat(name[1], kind[1], parent[1] if parent else None, fields, source))
    return records


def add_stats(mapping: dict, records: list[Stat]) -> None:
    for record in records:
        record.previous = mapping.get(record.name)
        mapping[record.name] = record


def resolve_stat(name: str, mapping: dict) -> tuple[dict, dict]:
    def visit(record: Stat, seen: set) -> tuple[dict, dict]:
        if id(record) in seen:
            raise ValueError(f"Stats inheritance cycle: {record.name}")
        seen = seen | {id(record)}
        values, sources = {}, {}
        if record.parent:
            parent = record.previous if record.parent == record.name else mapping.get(record.parent)
            if parent is None:
                raise ValueError(f"Missing parent: {record.name} -> {record.parent}")
            values, sources = visit(parent, seen)
        values.update(record.fields)
        sources.update({key: f"{record.source}:{record.name}" for key in record.fields})
        return values, sources
    if name not in mapping:
        raise ValueError(f"Unknown Stats record: {name}")
    return visit(mapping[name], set())


def read_roots(path: Path) -> dict:
    result = {}
    for node in ET.parse(path).findall('.//node[@id="GameObjects"]'):
        fields = {a.get("id"): dict(a.attrib) for a in node.findall("attribute")}
        key = fields.get("MapKey", {}).get("value")
        if key:
            result[key] = fields
    return result


def resolve_root(identifier: str, roots: dict) -> dict:
    def visit(key: str, seen: set) -> dict:
        if key in seen or key not in roots:
            raise ValueError(f"Missing or cyclic RootTemplate: {key}")
        current = roots[key]
        parent = current.get("ParentTemplateId", {}).get("value")
        values = visit(parent, seen | {key}) if parent and parent != "00000000-0000-0000-0000-000000000000" else {}
        values.update(current)
        return values
    return visit(identifier, set())


def category(kind: str, values: dict) -> str:
    if kind == "Weapon":
        return "weapon"
    if values.get("Shield") == "Yes":
        return "shield"
    return {"Breast": "body", "Helmet": "head", "Gloves": "gloves", "Boots": "boots",
            "Ring": "ring", "Amulet": "amulet", "Cloak": "cloak",
            "Underwear": "clothing", "VanityBody": "clothing", "VanityBoots": "clothing"}.get(values.get("Slot"), "equipment")


def build_catalog() -> dict:
    stats, roots, inputs = {}, {}, {}
    def fingerprint(path: Path) -> None:
        inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for module, stat_folder, root_folder in MODULES:
        for kind in ("Weapon", "Armor"):
            path = ROOT / ".tools" / stat_folder / "Public" / module / "Stats/Generated/Data" / (kind + ".txt")
            if path.exists():
                fingerprint(path)
                add_stats(stats, parse_stats(path.read_text(encoding="utf-8-sig"), f"{module}/{kind}.txt"))
        path = ROOT / ".tools" / root_folder / "Public" / module / "RootTemplates/_merged.lsx"
        if path.exists():
            fingerprint(path)
            for key, fields in read_roots(path).items():
                roots.setdefault(key, {}).update(fields)
    # A separate view describes Honour rules without copying them into generated mods.
    honour = dict(stats)
    for kind in ("Weapon", "Armor"):
        path = ROOT / ".tools/healing-word-Gustav/Public/Honour/Stats/Generated/Data" / (kind + ".txt")
        if path.exists():
            fingerprint(path)
            add_stats(honour, parse_stats(path.read_text(encoding="utf-8-sig"), f"Honour/{kind}.txt"))
    language = ROOT / ".tools/equipment-chinese.xml"
    fingerprint(language)
    strings = {}
    for content in ET.parse(language).getroot():
        strings[(content.get("contentuid"), content.get("version"))] = content.text or ""
    resolved = {}
    rejected = Counter()
    for key in roots:
        try:
            values = resolve_root(key, roots)
        except ValueError:
            rejected["root_inheritance_unresolved"] += 1
            continue
        if values.get("Type", {}).get("value") == "item":
            resolved[key] = values
    handle_users = {}
    for key, values in resolved.items():
        handle = values.get("DisplayName", {}).get("handle")
        if handle:
            handle_users.setdefault(handle, []).append(key)
    items = {}
    for key, template in resolved.items():
        record = template.get("Stats", {}).get("value")
        if record not in stats or stats[record].kind not in ("Weapon", "Armor"):
            continue
        if record.startswith("_") or record == "NoWeapon":
            rejected["internal_base_stats"] += 1
            continue
        try:
            uuid.UUID(key)
            normal, source = resolve_stat(record, stats)
            honour_values, _ = resolve_stat(record, honour)
        except (ValueError, KeyError):
            rejected["stats_inheritance_unresolved"] += 1
            continue
        display = template.get("DisplayName", {})
        handle, version = display.get("handle"), display.get("version")
        title = strings.get((handle, version))
        if not title or not title.strip() or "<" in title or title.startswith("[WIP]"):
            rejected["no_plain_chinese_name"] += 1
            continue
        if normal.get("InventoryTab") != "Equipment":
            rejected["not_equipment_inventory"] += 1
            continue
        if template.get("IsDeleted", {}).get("value", "false").lower() == "true":
            rejected["deleted_template"] += 1
            continue
        capabilities, blocked = ["rarity"], {}
        if re.fullmatch(r"\d+(?:\.\d+)?", normal.get("Weight", "")):
            capabilities.append("weight_kg")
        else:
            blocked["weight_kg"] = "Weight original value is unresolved."
        if stats[record].kind == "Weapon":
            for product, field in [("damage", "Damage"), ("versatile_damage", "VersatileDamage")]:
                if all(re.fullmatch(r"\d+d\d+", values.get(field, "")) for values in (normal, honour_values)):
                    capabilities.append(product)
                else:
                    blocked[product] = f"{field} has no resolved dice value in both rule views."
        else:
            blocked["damage"] = "This object is not Weapon Stats."
            blocked["versatile_damage"] = "This object is not Weapon Stats."
        users = handle_users.get(handle, [])
        # A text override affects every reference to this handle, not just the chosen UUID.
        different_records = {resolved[user].get("Stats", {}).get("value") for user in users}
        if different_records == {record}:
            capabilities.append("name")
        else:
            blocked["name"] = "Chinese name handle is shared by different or unresolved Stats records."
        object_id = "equipment:" + key
        items[object_id] = {
            "object_id": object_id, "display_name": title, "category": category(stats[record].kind, normal),
            "root_uuid": key, "root_name": template.get("Name", {}).get("value"),
            "record": record, "stats_type": stats[record].kind,
            "name_handle": handle, "name_version": version,
            "name_reference_templates": users, "capabilities": sorted(capabilities), "blocked_fields": blocked,
            "original": {field: normal.get(field) for field in FIELDS},
            "honour_original": {field: honour_values.get(field) for field in FIELDS},
            "field_sources": {field: source.get(field) for field in FIELDS},
            "game_validation": "user_reported_damage_2d6" if key == "1e172d76-3433-4ee7-ae1a-9e7d8ae0f12b" else "not_performed",
            "scope": "Stats edits affect all items using this record and may affect descendants; availability in player saves is not verified.",
        }
    stats_roots = {}
    for item in items.values():
        stats_roots.setdefault(item["record"], []).append(item["root_uuid"])
    for item in items.values():
        item["shared_record_templates"] = stats_roots[item["record"]]
    descendants = {record: set() for record in stats_roots}
    for record in stats.values():
        current, seen = record, set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if current.name != record.name and current.name in descendants:
                descendants[current.name].add(record.name)
            current = current.previous if current.parent == current.name else stats.get(current.parent)
    for item in items.values():
        item["descendant_records"] = sorted(descendants[item["record"]])
    counts = Counter(item["category"] for item in items.values())
    field_counts = Counter(field for item in items.values() for field in item["capabilities"])
    return {"catalog_version": "equipment-mvp-v1", "snapshot_date": "2026-10-13",
            "game_version_context": "v4.1.1.7631656 (from user screenshot, not executable inspection)",
            "sources_sha256": inputs, "stats_records": len(stats), "root_templates": len(roots),
            "items_count": len(items), "unique_equipment_stats": len(stats_roots), "category_counts": dict(counts), "capability_counts": dict(field_counts),
            "excluded_counts": dict(rejected), "items": items,
            "coverage_note": "Identified candidates from extracted vanilla sources, not all player-obtainable gear or all game-tested objects."}


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("catalog_version") != "equipment-mvp-v1" or not isinstance(data.get("items"), dict):
        raise ValueError("Unsupported equipment catalog format.")
    return data


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    args = parser.parse_args()
    data = build_catalog()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: data[key] for key in ("catalog_version", "items_count", "category_counts", "capability_counts", "excluded_counts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
