"""Read-only index of extracted native data; never treats discovery as support."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from scripts.equipment_catalog import ROOT, MODULES, add_stats, parse_stats, resolve_stat, read_roots, resolve_root
from scripts.resource_audit_v11 import audit_expression, honour_diff, audit_assets, acquisition_mapping


def build_catalog():
    stats, roots, inputs, root_sources = {}, {}, {}, {}
    diagnostics = []
    def fingerprint(path):
        key = path.relative_to(ROOT).as_posix()
        inputs[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        return key

    # Explicit module precedence; Honour is a separate ruleset, never merged into normal.
    for module, stat_folder, root_folder in MODULES:
        folder = ROOT / '.tools' / stat_folder / 'Public' / module / 'Stats/Generated/Data'
        if not folder.exists():
            diagnostics.append({'code': 'missing_module', 'module': module})
        for path in sorted(folder.glob('*.txt')):
            source = fingerprint(path)
            add_stats(stats, parse_stats(path.read_text(encoding='utf-8-sig'), source))
        path = ROOT / '.tools' / root_folder / 'Public' / module / 'RootTemplates/_merged.lsx'
        if path.exists():
            source = fingerprint(path)
            for key, fields in read_roots(path).items():
                roots.setdefault(key, {}).update(fields)
                root_sources.setdefault(key, {}).update({field: source for field in fields})

    records = {}
    for name, record in sorted(stats.items()):
        if record.kind not in {'Weapon', 'Armor', 'PassiveData', 'StatusData', 'SpellData'}:
            continue
        try:
            effective, sources = resolve_stat(name, stats)
        except ValueError as error:
            diagnostics.append({'code': 'stats_inheritance', 'id': name, 'detail': str(error)})
            continue
        references = []
        for field in ('PassivesOnEquip', 'StatusOnEquip'):
            expected = 'PassiveData' if field == 'PassivesOnEquip' else 'StatusData'
            for ref in filter(None, (x.strip() for x in effective.get(field, '').split(';'))):
                valid = ref in stats and stats[ref].kind == expected
                references.append({'field': field, 'id': ref, 'exists_with_expected_type': valid})
                if not valid:
                    diagnostics.append({'code': 'missing_reference', 'id': name, 'field': field, 'target': ref})
        records[name] = {'type': record.kind, 'parent': record.parent, 'source': record.source,
                         'raw': record.fields, 'effective': effective, 'field_sources': sources,
                         'references': references,
                         'expression_reference_check': 'not_implemented',
                         'generation_ready': False}
    honour = honour_diff(stats, fingerprint)
    asset_icons, visuals = audit_assets(fingerprint)
    model_listing = ROOT / 'build/v1.1/models-pak.log'
    model_paths = set()
    if model_listing.exists():
        fingerprint(model_listing)
        model_paths = {line.split('\t')[0].casefold() for line in model_listing.read_text(encoding='utf-8-sig').splitlines()}
    expression_fields = ('Boosts', 'DefaultBoosts', 'BoostsOnEquipMainHand', 'StatsFunctors',
                         'OnApplyFunctors', 'OnRemoveFunctors', 'SpellProperties', 'SpellSuccess', 'SpellFail')
    for record in records.values():
        audits = {field: audit_expression(record['effective'][field], records) for field in expression_fields
                  if record['effective'].get(field)}
        record['expression_reference_check'] = audits
        record['unreviewed_fields'] = sorted(set(record['effective']) - set(expression_fields) -
                                             {'PassivesOnEquip', 'StatusOnEquip', 'DisplayName', 'Description', 'Icon'})
    templates = {}
    for key in sorted(roots):
        try:
            fields = resolve_root(key, roots)
        except ValueError as error:
            diagnostics.append({'code': 'template_inheritance', 'id': key, 'detail': str(error)})
            continue
        if fields.get('Type', {}).get('value') != 'item':
            continue
        stat = fields.get('Stats', {}).get('value')
        if stat not in records or records[stat]['type'] not in {'Weapon', 'Armor'}:
            continue
        field_sources = {}
        ancestry = []
        ancestor = key
        while ancestor and ancestor != '00000000-0000-0000-0000-000000000000':
            ancestry.append(ancestor)
            ancestor = roots[ancestor].get('ParentTemplateId', {}).get('value')
        for ancestor in reversed(ancestry):
            field_sources.update(root_sources[ancestor])
        templates[key] = {'stats': stat, 'parent_template': roots[key].get('ParentTemplateId', {}).get('value'),
                          'raw': roots[key], 'effective': fields, 'direct_field_sources': root_sources[key],
                          'effective_field_sources': field_sources,
                          'modify_eligibility': 'use_v1_catalog_and_presentation',
                          'create_eligibility': 'pending_visual_and_acquisition_review'}
        icon = fields.get('Icon', {}).get('value')
        visual = fields.get('VisualTemplate', {}).get('value')
        asset = visuals.get(visual, {})
        visual_fields = asset.get('fields', {})
        reasons = []
        if records[stat]['type'] != 'Weapon':
            reasons.append('armor_race_body_mapping_not_reviewed')
        if not asset_icons.get(icon, {}).get('asset_exists'):
            reasons.append('icon_atlas_not_verified')
        if not visual_fields or visual_fields.get('SourceFile', '').casefold() not in model_paths:
            reasons.append('visual_model_not_verified')
        if visual_fields.get('SkeletonResource') or visual_fields.get('NeedsSkeletonRemap') != 'False':
            reasons.append('skeleton_mapping_not_reviewed')
        templates[key]['create_eligibility'] = {'status': 'blocked' if reasons else 'base_template_qualified',
              'reasons': reasons, 'scope': 'inherit_same_weapon_appearance_no_visual_swap',
              'visual': asset, 'icon': asset_icons.get(icon), 'generation_ready': False,
              'body_policy': 'unchanged rigid weapon attachment only; no new race/body fitting claim'}
    icons = sorted({r['effective']['Icon'] for r in records.values() if r['effective'].get('Icon')})
    fields = {}
    for kind in ('Weapon', 'Armor', 'PassiveData', 'StatusData', 'SpellData'):
        fields[kind] = sorted({f for r in records.values() if r['type'] == kind for f in r['effective']})
    acquisition = []
    treasure = ROOT / '.tools/v11-acquisition/Public/Gustav/Stats/Generated/TreasureTable.txt'
    if treasure.exists():
        source = fingerprint(treasure)
        match = re.search(r'^new treasuretable "DEN_Weaponsmith_Trade"\n(.*?)(?=^new treasuretable |\Z)',
                          treasure.read_text(encoding='utf-8-sig'), re.M | re.S)
        if match:
            acquisition.append({'id': 'dammon_act1', 'table': 'DEN_Weaponsmith_Trade',
                                'source': source, 'raw': match.group(0),
                                'chapter': 'Act 1', 'location': 'Emerald Grove',
                                'location_evidence': 'https://bg3.wiki/wiki/Dammon',
                                'evidence_level': 'local_table_confirmed_npc_mapping_community_source',
                                'limitations': ['NPC must be alive and still accessible',
                                                'Existing stock refresh and new-save requirement unverified',
                                                'Other acts use different tables; no automatic fallback'],
                                'generation_ready': False})
    mapping = acquisition_mapping(fingerprint)
    for entry in acquisition:
        entry['npc_mapping'] = mapping
        entry['evidence_level'] = 'local_entity_and_table' if mapping and mapping['matched'] else 'table_only'
    return {'schema_version': '1.1-resource-1', 'ruleset': 'normal', 'inputs_sha256': inputs,
            'records': records, 'templates': templates, 'icon_references': icons,
            'icon_asset_validation': asset_icons, 'honour': honour, 'observed_fields': fields,
            'unknown_field_policy': 'preserve_for_inspection_never_generate_without_capability_rule',
            'acquisition_entries': acquisition, 'diagnostics': diagnostics,
            'limitations': ['Unknown functions/fields blocked; this is not a full BG3 expression compiler',
                           'Acquisition merging is phase B; refresh and existing saves require later game validation',
                           'Only unchanged rigid weapon visuals qualified; armor body fitting blocked',
                           'Extracted vanilla modules are indexed; installed hotfix overlays are not certified'],
            'counts': dict(Counter(r['type'] for r in records.values()))}


if __name__ == '__main__':
    result = build_catalog()
    output = ROOT / 'build/v1.1/resource-catalog.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {k: result[k] for k in ('schema_version', 'ruleset', 'inputs_sha256', 'counts', 'limitations')}
    summary.update(templates=len(result['templates']), icons=len(result['icon_references']),
                   qualified_weapon_templates=sum(t['create_eligibility']['status'] == 'base_template_qualified' for t in result['templates'].values()),
                   honour_changed_records=len(result['honour']['differences']),
                   acquisition_entries=result['acquisition_entries'],
                   diagnostics=dict(Counter(d['code'] for d in result['diagnostics'])))
    (ROOT / 'data/v1.1/resource-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'inputs_sha256'}, ensure_ascii=False))
