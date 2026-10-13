import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts.generate_mod import DIVINE, OLD_PASSIVE, ROOT, ValidationError, generate, no_duplicate_keys, render_files, validate_request

ID = "00000000-0000-4000-8000-000000000001"


class ParameterizedTests(unittest.TestCase):
    def test_recorded_values_work_without_experimental(self):
        cases = [
            {"object": "first_blood_shortsword", "changes": {"damage": "2d6"}},
            {"object": "first_blood_shortsword", "changes": {"dexterity_bonus": 2}},
            {"object": "first_blood_shortsword", "changes": {"name": "曙光短剑"}},
            {"object": "first_blood_shortsword", "changes": {"passive_mode": "replace_with_alert"}},
            {"object": "healing_word", "changes": {"cast_distance_m": 36}},
        ]
        for request in cases:
            with self.subTest(request=request):
                _, warnings = validate_request(request)
                self.assertFalse(warnings)

    def test_invalid_input_rejected_even_in_experimental_mode(self):
        cases = [("damage", "0d6"), ("damage", "11d6"), ("damage", "2d7"),
                 ("damage", '2d6"\ndata "DefaultBoosts" "bad'),
                 ("dexterity_bonus", True), ("dexterity_bonus", 2.0), ("dexterity_bonus", 0),
                 ("name", ""), ("name", "a" * 61), ("name", "bad\nname"), ("name", "\ud800"), ("name", "\uffff"),
                 ("passive_mode", "ArbitraryPassive"), ("DefaultBoosts", "anything")]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                validate_request({"object": "first_blood_shortsword", "changes": {key: value}}, allow_unverified=True)
        for value in [True, "36", 0, 61, 1.25, float("nan"), float("inf")]:
            with self.subTest(distance=value), self.assertRaises(ValidationError):
                validate_request({"object": "healing_word", "changes": {"cast_distance_m": value}}, allow_unverified=True)

    def test_schema_and_object_restrictions(self):
        for request in [[], {}, {"object": "unknown", "changes": {"damage": "2d6"}},
                        {"object": "healing_word", "changes": {}},
                        {"object": "healing_word", "changes": {"damage": "2d6"}},
                        {"object": "healing_word", "changes": {"cast_distance_m": 36}, "code": "bad"}]:
            with self.subTest(request=request), self.assertRaises(ValidationError):
                validate_request(request, allow_unverified=True)
        with self.assertRaises(ValidationError):
            json.loads('{"object":"one","object":"two"}', object_pairs_hook=no_duplicate_keys)

    def test_new_values_and_combination_require_explicit_experimental(self):
        request = {"object": "first_blood_shortsword", "changes": {"damage": "3d6", "dexterity_bonus": 3, "passive_mode": "replace_with_alert"}}
        with self.assertRaises(ValidationError):
            validate_request(request)
        clean, warnings = validate_request(request, allow_unverified=True)
        self.assertEqual(clean, request)
        self.assertEqual(len(warnings), 3)
        files = render_files(clean, ID)
        weapon = next(data.decode() for p, data in files.items() if p.name == "Weapon.txt")
        self.assertIn('data "Damage" "3d6"', weapon)
        self.assertRegex(weapon, 'data "PassivesOnEquip" "Alert;ModSuperman_Dexterity_')
        self.assertNotIn(OLD_PASSIVE, weapon)
        self.assertIn('data "DefaultBoosts" "WeaponProperty(Magical)"', weapon)

    def test_sparse_damage_does_not_change_mode_specific_effects(self):
        files = render_files({"object": "first_blood_shortsword", "changes": {"damage": "2d6"}}, ID)
        weapon = next(data.decode() for p, data in files.items() if p.name == "Weapon.txt")
        self.assertEqual(re.findall(r'^data "([^"]+)" "([^"]+)"', weapon, re.MULTILINE), [("Damage", "2d6")])

    def test_keep_and_dexterity_do_not_override_honour_boosts(self):
        for changes in [{"dexterity_bonus": 2}, {"passive_mode": "keep", "dexterity_bonus": 2}]:
            files = render_files({"object": "first_blood_shortsword", "changes": changes}, ID)
            weapon = next(data.decode() for p, data in files.items() if p.name == "Weapon.txt")
            self.assertNotIn("DefaultBoosts", weapon)
            self.assertIn(OLD_PASSIVE + ";ModSuperman_Dexterity_", weapon)

    def test_name_xml_is_escaped_and_creates_no_weapon_override(self):
        files = render_files({"object": "first_blood_shortsword", "changes": {"name": '曙光<&"短剑'}}, ID)
        self.assertFalse(any(p.name == "Weapon.txt" for p in files))
        xml = next(data for p, data in files.items() if p.name == "chinese.xml")
        self.assertEqual(ET.fromstring(xml).find("content").text, '曙光<&"短剑')

    def test_fractional_distance_changes_only_one_runtime_field(self):
        files = render_files({"object": "healing_word", "changes": {"cast_distance_m": 24.5}}, ID)
        text = next(data for p, data in files.items() if p.name == "Spell_Target.txt")
        baseline = (ROOT / "samples/healing-word/before/runtime-stats/Generated/Data/Spell_Target.txt").read_bytes()
        self.assertEqual(text.replace(b'data "TargetRadius" "24.5"', b'data "TargetRadius" "18"'), baseline)

    def test_requires_confirmation_and_rejects_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            with self.assertRaises(ValidationError):
                generate({"object": "healing_word", "changes": {"cast_distance_m": 36}}, root)
            self.assertFalse(root.exists())
            with self.assertRaises(ValidationError):
                generate({"object": "healing_word", "changes": {"cast_distance_m": 999}}, root, confirmed=True)
            self.assertFalse(root.exists())

    def test_package_failure_records_failure_without_claiming_game_success(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.generate_mod.run_tool", side_effect=RuntimeError("simulated pack failure")):
            root = Path(directory)
            with self.assertRaises(RuntimeError):
                generate({"object": "healing_word", "changes": {"cast_distance_m": 36}}, root, confirmed=True)
            manifest = json.loads(next(root.glob("*/result.json")).read_text(encoding="utf-8"))
            self.assertEqual(manifest["package_check"], "failed")
            self.assertEqual(manifest["game_validation"], "not_performed")


if __name__ == "__main__":
    unittest.main()
