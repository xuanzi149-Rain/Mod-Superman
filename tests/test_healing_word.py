from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.generate_healing_word import EDITOR, MODULE, MODULE_UUID, ROOT, RUNTIME, generate_files, module_metadata, write_output


class HealingWordTests(unittest.TestCase):
    def test_only_radius_changes_in_both_sources(self):
        template = ROOT / "samples/healing-word/before"
        output = generate_files(template, confirmed=True)
        original_runtime = (template / RUNTIME).read_bytes()
        self.assertEqual(output[RUNTIME].replace(b'data "TargetRadius" "36"', b'data "TargetRadius" "18"', 1), original_runtime)
        original = ET.fromstring((template / EDITOR).read_bytes())
        generated = ET.fromstring(output[EDITOR])
        radius = generated.find('.//field[@name="TargetRadius"]')
        self.assertEqual(radius.get("value"), "36")
        radius.set("value", "18")
        self.assertEqual(ET.tostring(original), ET.tostring(generated))

    def test_requires_confirmation(self):
        with self.assertRaises(ValueError):
            generate_files(ROOT / "samples/healing-word/before", confirmed=False)

    def test_changed_or_missing_baseline_does_not_create_output(self):
        for relative, replacement in [(RUNTIME, b'new entry "WrongSpell"'), (EDITOR, b'<broken>')]:
            with self.subTest(file=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(ROOT / "samples/healing-word/before", root / "template")
                (root / "template" / relative).write_bytes(replacement)
                with self.assertRaises(ValueError):
                    write_output(root / "template", root / "output", confirmed=True)
                self.assertFalse((root / "output").exists())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                write_output(root / "missing", root / "output", confirmed=True)
            self.assertFalse((root / "output").exists())

    def test_package_identity_and_no_unrelated_scripts(self):
        tree = ET.fromstring(module_metadata())
        info = tree.find('.//node[@id="ModuleInfo"]')
        fields = {a.get("id"): a.get("value") for a in info.findall("attribute")}
        self.assertEqual(fields["UUID"], MODULE_UUID)
        self.assertEqual(fields["Folder"], MODULE)
        self.assertIsNone(info.find("children"))

    def test_runtime_package_source_matches_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            write_output(ROOT / "samples/healing-word/before", output, confirmed=True)
            path = output / "mod-source/Public" / MODULE / "Stats/Generated/Data/Spell_Target.txt"
            self.assertEqual(path.read_bytes(), (output / RUNTIME).read_bytes())
            with self.assertRaises(FileExistsError):
                write_output(ROOT / "samples/healing-word/before", output, confirmed=True)


if __name__ == "__main__":
    unittest.main()
