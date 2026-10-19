"""Conservative reference and asset audit. Unknown syntax is never approved."""
import re
import xml.etree.ElementTree as ET
from scripts.equipment_catalog import ROOT, add_stats, parse_stats, resolve_stat

REFERENCE_ARGS = {'UnlockSpell': ('SpellData', 0), 'ApplyStatus': ('StatusData', 0),
                  'HasStatus': ('StatusData', 0), 'RemoveStatus': ('StatusData', 0)}


def calls(text):
    """Find nested calls and split top-level arguments, respecting quoted strings."""
    found, stack, quote = [], [], None
    for i, char in enumerate(text):
        if quote:
            if char == quote and (i == 0 or text[i-1] != '\\'):
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == '(':
            match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', text[:i])
            stack.append([match[1] if match else '', i+1, []])
        elif char == ',' and stack:
            stack[-1][2].append(text[stack[-1][1]:i].strip())
            stack[-1][1] = i+1
        elif char == ')':
            if not stack:
                raise ValueError('Unbalanced expression')
            name, start, args = stack.pop()
            args.append(text[start:i].strip())
            if name:
                found.append((name, args))
    if quote or stack:
        raise ValueError('Unbalanced expression')
    return found


def audit_expression(text, records):
    references, unresolved = [], []
    try:
        parsed = calls(text)
    except ValueError as error:
        return {'references': [], 'unresolved': [str(error)], 'status': 'blocked'}
    for name, args in parsed:
        if name not in REFERENCE_ARGS:
            unresolved.append('unreviewed_function:' + name)
            continue
        kind, index = REFERENCE_ARGS[name]
        # ApplyStatus(SELF,status,...) and ApplyStatus(status,...).
        if name == 'ApplyStatus' and args and args[0] in ('SELF', 'TARGET', 'OWNER'):
            index = 1
        if len(args) <= index:
            unresolved.append('missing_argument:' + name)
            continue
        ref = args[index].strip("\"'")
        valid = ref in records and records[ref]['type'] == kind
        references.append({'function': name, 'id': ref, 'expected_type': kind, 'valid': valid})
    if text.strip() and not parsed:
        unresolved.append('unparsed_expression')
    return {'references': references, 'unresolved': sorted(set(unresolved)),
            'status': 'checked' if not unresolved and all(r['valid'] for r in references) else 'blocked'}


def honour_diff(stats, fingerprint):
    overlay = dict(stats)
    for folder, module in [('healing-word-Gustav', 'Honour'), ('healing-word-GustavX', 'HonourX')]:
        for path in sorted((ROOT / '.tools' / folder / 'Public' / module / 'Stats/Generated/Data').glob('*.txt')):
            add_stats(overlay, parse_stats(path.read_text(encoding='utf-8-sig'), fingerprint(path)))
    differences, errors = {}, []
    # Resolve all records, including children affected by changed ancestors.
    for name in sorted(overlay):
        try:
            effective, sources = resolve_stat(name, overlay)
            original = resolve_stat(name, stats)[0] if name in stats else {}
            changed = {f: {'normal': original.get(f), 'honour': effective.get(f), 'source': sources.get(f)}
                       for f in original.keys() | effective.keys() if original.get(f) != effective.get(f)}
            if changed:
                differences[name] = changed
        except ValueError as error:
            errors.append({'id': name, 'error': str(error)})
    return {'differences': differences, 'errors': errors, 'patch_order': ['normal', 'Honour', 'HonourX']}


def audit_assets(fingerprint):
    icons, visuals = {}, {}
    listing = ROOT / 'build/v1.1/icons-pak.log'
    atlas_paths = {line.split('\t')[0] for line in listing.read_text(encoding='utf-8-sig').splitlines()} if listing.exists() else set()
    if listing.exists():
        fingerprint(listing)
    for path in sorted((ROOT / '.tools/v11-assets/Public').glob('*/GUI/*.lsx')):
        source = fingerprint(path)
        tree = ET.parse(path)
        atlas = tree.find('.//node[@id="TextureAtlasPath"]/attribute[@id="Path"]')
        if atlas is None:
            continue
        module = path.relative_to(ROOT / '.tools/v11-assets/Public').parts[0]
        asset = 'Public/' + module + '/' + atlas.get('value')
        for node in tree.findall('.//node[@id="IconUV"]'):
            key = node.find('attribute[@id="MapKey"]')
            if key is not None:
                icons[key.get('value')] = {'source': source, 'atlas': asset, 'asset_exists': asset in atlas_paths}
    for path in sorted((ROOT / '.tools/v11-assets/Public/Shared/Content/Assets/Weapons').rglob('*.lsx')):
        source = fingerprint(path)
        for node in ET.parse(path).iter('node'):
            fields = {a.get('id'): a.get('value') for a in node.findall('attribute')}
            if fields.get('ID'):
                visuals[fields['ID']] = {'source': source, 'fields': fields}
    return icons, visuals


def acquisition_mapping(fingerprint):
    path = ROOT / '.tools/v11-assets/characters.lsx'
    if not path.exists():
        return None
    source = fingerprint(path)
    for node in ET.parse(path).iter('node'):
        attrs = {a.get('id'): a.get('value') for a in node.findall('attribute')}
        if attrs.get('MapKey') == 'e2ad06ec-8034-479a-9f69-b86faea6dc79':
            tables = [a.get('value') for a in node.findall('.//node[@id="TradeTreasures"]//attribute[@id="Object"]')]
            return {'source': source, 'uuid': attrs['MapKey'], 'name': attrs.get('Name'), 'tables': tables,
                    'matched': 'DEN_Weaponsmith_Trade' in tables}
    return None
