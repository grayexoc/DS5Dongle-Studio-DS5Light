"""Check that published instructions match the source package's contents."""
import ast
import json
from pathlib import Path
import unittest

from app_version import APP_VERSION

ROOT = Path(__file__).resolve().parent


class ReleaseMetadataTests(unittest.TestCase):
    def test_download_examples_use_the_app_version(self):
        self.assertRegex(APP_VERSION, r'^\d+\.\d+\.\d+$')
        package = f'DS5Light-win-x64-v{APP_VERSION}.zip'
        for name in ('README.md', 'PRODUCT_KO.md', 'SETUP.md', 'SETUP_KO.md', 'RELEASE_NOTES.md'):
            with self.subTest(document=name):
                self.assertIn(package, (ROOT / name).read_text(encoding='utf-8-sig'))

    def test_setup_uses_the_actual_app_presets_and_defaults(self):
        tree = ast.parse((ROOT / 'studio_recommended.py').read_text(encoding='utf-8-sig'))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'PRESETS' for t in n.targets))
        filenames = [ast.literal_eval(row.elts[0]) for row in assignment.value.elts]
        build = (ROOT / 'build.ps1').read_text(encoding='utf-8-sig')
        for name in ('SETUP.md', 'SETUP_KO.md', 'Studio Presert/README.txt', 'Studio Presert/README_KO.txt'):
            text = (ROOT / name).read_text(encoding='utf-8-sig')
            for filename in filenames:
                self.assertTrue((ROOT / 'Studio Presert' / filename).is_file())
                self.assertIn(filename, text)
                self.assertIn(filename, build)
        defaults = json.loads((ROOT / 'default_config.json').read_text(encoding='utf-8-sig'))
        self.assertFalse(defaults['bypass'])
        for name in ('SETUP.md', 'SETUP_KO.md'):
            text = (ROOT / name).read_text(encoding='utf-8-sig')
            for value in ('strength', 'impact', 'gain'):
                self.assertIn(f"{defaults[value] * 100:g}%", text)

    def test_build_packages_the_linked_setup_documents(self):
        build = (ROOT / 'build.ps1').read_text(encoding='utf-8-sig')
        for name in ('README.md', 'PRODUCT_KO.md', 'SETUP.md', 'SETUP_KO.md', 'RELEASE_NOTES.md'):
            self.assertIn(name, build)
            self.assertTrue((ROOT / name).is_file())


if __name__ == '__main__':
    unittest.main()
