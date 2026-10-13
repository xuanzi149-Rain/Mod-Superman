from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.generate_equipment_extension import DEX_PASSIVE, KINDS, NAME_HANDLE, OBJECT, OLD_PASSIVE, generate_files, identity, write_output


class EquipmentExtensionTests(unittest.TestCase):
    def test_name_uses_original_handle_and_contains_no_stats_override(self):
        files = generate_files("name", confirmed=True)
        self.assertFalse(any(p.suffix == ".txt" for p in files))
        localized = next(data for p, data in files.items() if p.name == "chinese.xml")
        entry = ET.fromstring(localized).find("content")
        self.assertEqual(entry.get("contentuid"), NAME_HANDLE)
        self.assertEqual(entry.get("version"), "2")
        self.assertEqual(entry.text, "曙光短剑")

    def test_dexterity_adds_passive_preserving_old_passive_and_mode_boosts(self):
        files = generate_files("dexterity", confirmed=True)
        weapon = next(data.decode() for p, data in files.items() if p.name == "Weapon.txt")
        self.assertEqual(re.findall(r'^data "([^"]+)" "([^"]+)"', weapon, re.MULTILINE), [("PassivesOnEquip", OLD_PASSIVE + ";" + DEX_PASSIVE)])
        passive = next(data.decode() for p, data in files.items() if p.name == "Passive.txt")
        self.assertIn('data "Boosts" "Ability(Dexterity,2)"', passive)
        xml = ET.fromstring(next(data for p, data in files.items() if p.name == "chinese.xml"))
        handles = {node.get("contentuid") for node in xml}
        self.assertIn("ModSupermanDexterityName", handles)

    def test_alert_deliberately_removes_both_original_damage_routes(self):
        files = generate_files("alert", confirmed=True)
        weapon = next(data.decode() for p, data in files.items() if p.name == "Weapon.txt")
        self.assertEqual(re.findall(r'^data "([^"]+)" "([^"]+)"', weapon, re.MULTILINE), [("PassivesOnEquip", "Alert"), ("DefaultBoosts", "WeaponProperty(Magical)")])
        self.assertNotIn("WeaponDamage", weapon)
        self.assertNotIn(OLD_PASSIVE, weapon)

    def test_independent_identities_and_only_target_record(self):
        self.assertEqual(len({identity(kind)[1] for kind in KINDS}), 3)
        for kind in KINDS:
            files = generate_files(kind, confirmed=True)
            for p, data in files.items():
                if p.name == "Weapon.txt":
                    self.assertIn(f'using "{OBJECT}"', data.decode())
                    self.assertNotIn(b'data "Damage"', data)

    def test_unconfirmed_or_unsupported_requests_rejected(self):
        with self.assertRaises(ValueError):
            generate_files("name", confirmed=False)
        with self.assertRaises(ValueError):
            generate_files("unknown", confirmed=True)

    def test_no_overwriting_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            write_output(output, confirmed=True)
            with self.assertRaises(FileExistsError):
                write_output(output, confirmed=True)


if __name__ == "__main__":
    unittest.main()
