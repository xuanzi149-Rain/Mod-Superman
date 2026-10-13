import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.equipment_catalog import Stat, add_stats, load_catalog, resolve_stat, resolve_root
from scripts.generate_equipment import FIRST_BLOOD, ValidationError, generate, render_files, validate_request
from scripts.generate_mod import no_duplicate_keys

ID = "00000000-0000-4000-8000-000000000001"


class CatalogTests(unittest.TestCase):
    def test_self_override_preserves_honour_fields(self):
        records = {}
        add_stats(records, [Stat('Base', 'Weapon', None, {'Damage': '1d6'}, 'Shared'),
                            Stat('Sword', 'Weapon', 'Base', {'PassivesOnEquip': 'Original'}, 'Gustav')])
        honour = dict(records)
        add_stats(honour, [Stat('Sword', 'Weapon', 'Sword', {'DefaultBoosts': 'HonourBonus'}, 'Honour')])
        add_stats(honour, [Stat('Sword', 'Weapon', 'Sword', {'Damage': '2d6'}, 'Mod')])
        values, _ = resolve_stat('Sword', honour)
        self.assertEqual(values, {'Damage': '2d6', 'PassivesOnEquip': 'Original', 'DefaultBoosts': 'HonourBonus'})
        self.assertEqual(resolve_stat('Sword', records)[0]['Damage'], '1d6')

    def test_missing_and_cyclic_parents_stop(self):
        for records in ({'A': Stat('A', 'Armor', 'missing', {}, 'test')},
                        {'A': Stat('A', 'Armor', 'B', {}, 'test'), 'B': Stat('B', 'Armor', 'A', {}, 'test')}):
            with self.assertRaises(ValueError):
                resolve_stat('A', records)

    def test_root_inheritance_and_cycle(self):
        roots = {'base': {'Stats': {'value': 'Sword'}, 'DisplayName': {'handle': 'h1'}},
                 'child': {'ParentTemplateId': {'value': 'base'}, 'Name': {'value': 'child'}}}
        self.assertEqual(resolve_root('child', roots)['Stats']['value'], 'Sword')
        roots['base']['ParentTemplateId'] = {'value': 'child'}
        with self.assertRaises(ValueError):
            resolve_root('child', roots)


class EquipmentMVPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_all_candidates_generate_only_requested_fields(self):
        values = {'damage': '2d6', 'versatile_damage': '2d8', 'weight_kg': 1.25, 'rarity': 'Rare', 'name': '测试装备'}
        for item in self.catalog['items'].values():
            changes = {field: values[field] for field in item['capabilities']}
            files = render_files({'object': item['object_id'], 'changes': changes}, ID, catalog=self.catalog)
            stats = next(value.decode() for path, value in files.items() if path.suffix == '.txt')
            expected_fields = {'Damage', 'VersatileDamage', 'Weight', 'Rarity'} & {
                {'damage': 'Damage', 'versatile_damage': 'VersatileDamage', 'weight_kg': 'Weight', 'rarity': 'Rarity'}.get(k) for k in changes}
            actual = {line.split('"')[1] for line in stats.splitlines() if line.startswith('data ')}
            self.assertEqual(actual, expected_fields)
            self.assertNotIn('DefaultBoosts', stats)
            self.assertNotIn('PassivesOnEquip', stats)
            self.assertFalse(any('RootTemplates' in str(path) for path in files))

    def test_damage_only_does_not_change_versatile_or_boosts(self):
        files = render_files({'object': FIRST_BLOOD, 'changes': {'damage': '2d6'}}, ID, catalog=self.catalog)
        stats = next(value.decode() for path, value in files.items() if path.suffix == '.txt')
        self.assertEqual(stats.count('data '), 1)
        self.assertIn('using "UND_Duergar_ShortswordOfFirstBlood"', stats)

    def test_invalid_values_and_schema(self):
        for field, value in [('damage', '11d6'), ('damage', '2d7'), ('damage', '1d6+3'),
                             ('weight_kg', True), ('weight_kg', '1'), ('weight_kg', -1),
                             ('weight_kg', 101), ('weight_kg', 0.0001), ('weight_kg', float('nan')),
                             ('rarity', 'rarE'), ('name', '\ud800'), ('name', 'bad\nname'), ('DefaultBoosts', 'bad')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                validate_request({'object': FIRST_BLOOD, 'changes': {field: value}}, catalog=self.catalog, allow_unverified=True)
        with self.assertRaises(ValidationError):
            json.loads('{"object":"a","object":"b"}', object_pairs_hook=no_duplicate_keys)

    def test_inapplicable_and_shared_name_fields_rejected(self):
        armour = next(i for i in self.catalog['items'].values() if i['stats_type'] == 'Armor')
        blocked = next(i for i in self.catalog['items'].values() if 'name' not in i['capabilities'])
        for item, field in [(armour, 'damage'), (blocked, 'name')]:
            with self.assertRaises(ValidationError):
                validate_request({'object': item['object_id'], 'changes': {field: '2d6'}}, catalog=self.catalog, allow_unverified=True)

    def test_name_escapes_xml_and_preserves_handle(self):
        files = render_files({'object': FIRST_BLOOD, 'changes': {'name': '曙光<&短剑'}}, ID, catalog=self.catalog)
        xml = next(data for path, data in files.items() if path.suffix == '.xml')
        content = ET.fromstring(xml).find('content')
        self.assertEqual(content.text, '曙光<&短剑')
        self.assertEqual(content.get('contentuid'), self.catalog['items'][FIRST_BLOOD]['name_handle'])
        self.assertFalse(any(path.suffix == '.txt' for path in files))

    def test_confirmation_and_experimental_gate_before_writes(self):
        request = {'object': FIRST_BLOOD, 'changes': {'weight_kg': 1}}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'output'
            with self.assertRaises(ValidationError):
                generate(request, output, allow_unverified=True)
            with self.assertRaises(ValidationError):
                generate(request, output, confirmed=True)
            self.assertFalse(output.exists())
        clean, warnings = validate_request({'object': FIRST_BLOOD, 'changes': {'damage': '2d6'}}, catalog=self.catalog)
        self.assertFalse(warnings)


if __name__ == '__main__':
    unittest.main()
