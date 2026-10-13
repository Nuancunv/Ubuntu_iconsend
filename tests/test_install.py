import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("manage", Path(__file__).resolve().parents[1] / "scripts/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iconsend-install-")
        self.prefix = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_install_upgrade_uninstall_and_keep_unrelated_file(self):
        manage.install(self.prefix)
        manage.install(self.prefix)
        unrelated = self.prefix / "share/applications/unrelated.desktop"
        unrelated.write_text("user file")
        manage.uninstall(self.prefix)
        self.assertFalse((self.prefix / "bin/ubuntu-iconsend").exists())
        self.assertFalse((self.prefix / "share/ubuntu-iconsend").exists())
        self.assertEqual(unrelated.read_text(), "user file")

    def test_refuses_destination_conflict_before_any_install(self):
        existing = self.prefix / "bin/ubuntu-iconsend"
        existing.parent.mkdir()
        existing.write_text("existing file")
        with self.assertRaises(manage.InstallError):
            manage.install(self.prefix)
        self.assertEqual(existing.read_text(), "existing file")
        self.assertFalse((self.prefix / "share/ubuntu-iconsend/launch.py").exists())

    def test_uninstall_keeps_modified_project_file(self):
        manage.install(self.prefix)
        modified = self.prefix / "share/ubuntu-iconsend/iconsend/core.py"
        modified.write_text("user modification")
        result = manage.uninstall(self.prefix)
        self.assertIn(str(modified), result)
        self.assertEqual(modified.read_text(), "user modification")


if __name__ == "__main__":
    unittest.main()
