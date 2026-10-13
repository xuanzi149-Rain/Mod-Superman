import shutil
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.generate_first_blood import EDITOR, ROOT, RUNTIME, generate_files, write_output


class FirstBloodTests(unittest.TestCase):
    def test_generated_bytes_equal_handmade_reference(self):
        generated = generate_files(ROOT / "samples/first-blood/before", confirmed=True)
        for relative in (EDITOR, RUNTIME):
            with self.subTest(file=relative):
                self.assertEqual(generated[relative], (ROOT / "samples/first-blood/after" / relative).read_bytes())

    def test_requires_confirmed_parameters(self):
        with self.assertRaises(ValueError):
            generate_files(ROOT / "samples/first-blood/before", confirmed=False)

    def test_invalid_baselines_are_rejected_before_output(self):
        replacements = [
            (RUNTIME, b'new entry "UND_Duergar_ShortswordOfFirstBlood"', b'new entry "UnknownWeapon"'),
            (RUNTIME, b'new entry ', b'new entry "UND_Duergar_ShortswordOfFirstBlood"\r\nnew entry '),
            (RUNTIME, b'data "Rarity" "Uncommon"', b'data "Rarity" "Rare"'),
            (RUNTIME, b'data "Unique" "1"', b'data "Unique" "1"\r\ndata "Damage" "1d6"'),
            (EDITOR, b'value="WeaponProperty(Magical)"', b'value="WeaponEnchantment(1)"'),
            (EDITOR, b'</fields>', b'<field name="Damage" value="1d6" /></fields>'),
            (EDITOR, b'</stats>', b'</broken>'),
        ]
        for relative, old, new in replacements:
            with self.subTest(file=relative, replacement=new), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                template = root / "template"
                shutil.copytree(ROOT / "samples/first-blood/before", template)
                file = template / relative
                file.write_bytes(file.read_bytes().replace(old, new, 1))
                with self.assertRaises((ValueError, ET.ParseError)):
                    write_output(template, root / "output", confirmed=True)
                self.assertFalse((root / "output").exists())

    def test_missing_template_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                write_output(root / "missing", root / "output", confirmed=True)
            self.assertFalse((root / "output").exists())

    def test_never_overwrites_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            write_output(ROOT / "samples/first-blood/before", output, confirmed=True)
            original = (output / RUNTIME).read_bytes()
            with self.assertRaises(FileExistsError):
                write_output(ROOT / "samples/first-blood/before", output, confirmed=True)
            self.assertEqual((output / RUNTIME).read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
