from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.generate_first_blood_v2 import MODULE, MODULE_UUID, OBJECT, ROOT, metadata, runtime_override, write_output


class FirstBloodV2Tests(unittest.TestCase):
    def test_override_contains_only_damage_and_retains_original_identity(self):
        text = runtime_override(confirmed=True).decode()
        self.assertEqual(re.findall(r'^new entry "([^"]+)"', text, re.MULTILINE), [OBJECT])
        self.assertEqual(re.findall(r'^using "([^"]+)"', text, re.MULTILINE), [OBJECT])
        self.assertEqual(re.findall(r'^data "([^"]+)" "([^"]+)"', text, re.MULTILINE), [("Damage", "2d6")])

    def test_shipped_mode_difference_is_preserved_by_omission(self):
        regular = (ROOT / "samples/first-blood/mode-source/Gustav-Weapon.txt").read_text()
        honour = (ROOT / "samples/first-blood/mode-source/Honour-Weapon.txt").read_text()
        passive = (ROOT / "samples/first-blood/mode-source/Honour-Passive.txt").read_text()
        self.assertIn('data "DefaultBoosts" "WeaponProperty(Magical)"', regular)
        self.assertIn('IF(HasMaxHPWithoutTemporaryHP(context.Target)):WeaponDamage(1d8, Piercing)', honour)
        self.assertIn(f'using "{OBJECT}"', honour)
        self.assertIn('data "StatsFunctors" ""', passive)
        # Verify emitted fields do not replace either mode's boosts/passive config.
        emitted = runtime_override(confirmed=True)
        self.assertNotIn(b'DefaultBoosts', emitted)
        self.assertNotIn(b'PassivesOnEquip', emitted)

    def test_requires_confirmation(self):
        with self.assertRaises(ValueError):
            runtime_override(confirmed=False)

    def test_existing_module_identity_and_new_version(self):
        info = ET.fromstring(metadata()).find('.//node[@id="ModuleInfo"]')
        fields = {a.get("id"): a.get("value") for a in info.findall("attribute")}
        self.assertEqual(fields["UUID"], MODULE_UUID)
        self.assertEqual(fields["Folder"], MODULE)
        self.assertEqual(fields["Version64"], "36028797018963971")

    def test_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "v2"
            write_output(output, confirmed=True)
            with self.assertRaises(FileExistsError):
                write_output(output, confirmed=True)


if __name__ == "__main__":
    unittest.main()
