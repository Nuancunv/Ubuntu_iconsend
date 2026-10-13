import concurrent.futures
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gi.repository import Gio, GLib

from iconsend.core import ReviewRequired, ShortcutError, create_shortcut, desktop_directory, inspect_launcher


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iconsend-core-")
        self.root = Path(self.temp.name)
        self.desktop = self.root / "自定义桌面"
        self.desktop.mkdir(mode=0o700)
        self.source = self.root / "中文应用.desktop"
        self.content = ("[Desktop Entry]\nType=Application\nName=测试应用\nName[zh_CN]=中文测试应用\n"
                        "Icon=utilities-terminal\nExec=/usr/bin/true %U\nTerminal=false\n"
                        "Actions=Example;\n\n[Desktop Action Example]\nName=示例\nExec=/usr/bin/true\n").encode()
        self.write(self.content)
        self.desktop_patch = mock.patch("iconsend.core.desktop_directory", return_value=self.desktop)
        self.desktop_patch.start()
        self.trust_patch = mock.patch("iconsend.core.set_trusted")
        self.trust_patch.start()

    def tearDown(self):
        self.desktop_patch.stop()
        self.trust_patch.stop()
        self.temp.cleanup()

    def write(self, content):
        self.source.write_bytes(content)
        self.source.chmod(0o600)

    def approved(self):
        record = inspect_launcher(self.source)
        return create_shortcut(record, record.digest)

    def test_unknown_source_requires_review_and_writes_nothing(self):
        record = inspect_launcher(self.source)
        self.assertFalse(record.trusted)
        with self.assertRaises(ReviewRequired):
            create_shortcut(record)
        self.assertEqual(list(self.desktop.iterdir()), [])

    def test_exact_copy_unicode_original_fields_and_permissions(self):
        path = self.approved()
        self.assertEqual(path.parent, self.desktop)
        self.assertEqual(path.read_bytes(), self.content)
        self.assertEqual(self.source.read_bytes(), self.content)
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        info = Gio.DesktopAppInfo.new_from_filename(str(path))
        self.assertEqual(info.get_string("Exec"), "/usr/bin/true %U")
        self.assertEqual(info.get_string("Icon"), "utilities-terminal")
        self.assertEqual(info.get_string("Name"), "测试应用")
        self.assertEqual(list(info.list_actions()), ["Example"])

    def test_duplicate_does_not_overwrite(self):
        first = self.approved()
        second = self.approved()
        self.assertNotEqual(first, second)
        self.assertIn("(2)", second.name)
        self.assertEqual(first.read_bytes(), self.content)

    def test_existing_symlink_is_never_followed_or_overwritten(self):
        victim = self.root / "existing-file"
        victim.write_text("unchanged")
        (self.desktop / self.source.name).symlink_to(victim)
        path = self.approved()
        self.assertIn("(2)", path.name)
        self.assertEqual(victim.read_text(), "unchanged")

    def test_concurrent_creation_is_exclusive(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _n: self.approved(), range(10)))
        self.assertEqual(len(set(results)), 10)
        self.assertTrue(all(p.read_bytes() == self.content for p in results))

    def test_stale_digest_is_rejected(self):
        record = inspect_launcher(self.source)
        self.write(self.content.replace(b"/usr/bin/true", b"/usr/bin/false"))
        with self.assertRaises(ShortcutError):
            create_shortcut(record, record.digest)
        self.assertEqual(list(self.desktop.iterdir()), [])

    def test_incorrect_approval_is_rejected(self):
        with self.assertRaises(ReviewRequired):
            create_shortcut(inspect_launcher(self.source), "not-the-current-digest")

    def test_trust_failure_rolls_back_only_new_file(self):
        existing = self.desktop / self.source.name
        existing.write_text("existing shortcut")
        with mock.patch("iconsend.core.set_trusted", side_effect=ShortcutError("GVfs unavailable")):
            with self.assertRaises(ShortcutError):
                self.approved()
        self.assertEqual(list(self.desktop.iterdir()), [existing])
        self.assertEqual(existing.read_text(), "existing shortcut")

    def test_invalid_missing_or_non_application_files(self):
        for content in (b"not a desktop file", b"[Desktop Entry]\nType=Link\nName=link\nURL=https://example.org\n",
                        b"[Desktop Entry]\nType=Application\nName=\nExec=/usr/bin/true\n",
                        b"[Desktop Entry]\nType=Application\nName=bad\nExec=/no/such/program\n",
                        b"[Desktop Entry]\nType=Application\nName=hidden\nExec=/usr/bin/true\nHidden=true\n",
                        b"[Desktop Entry]\nType=Application\nName=bad\nExec=/usr/bin/true\nTryExec=/no/such/program\n",
                        b"[Desktop Entry]\nType=Application\nName=bad\nExec=/usr/bin/true\x00\n"):
            with self.subTest(content=content):
                self.write(content)
                with self.assertRaises(ShortcutError):
                    inspect_launcher(self.source)
        with self.assertRaises(ShortcutError):
            inspect_launcher(self.root / "missing.desktop")
        with self.assertRaises(ShortcutError):
            inspect_launcher(self.root / "file.txt")

    def test_world_or_group_writable_source_is_rejected(self):
        for mode in (0o666, 0o664):
            self.source.chmod(mode)
            with self.assertRaises(ShortcutError):
                inspect_launcher(self.source)

    def test_dbus_duplicate_preserves_exec_and_disables_dbus(self):
        self.write(self.content + b"\n")
        self.write(self.content.replace(b"Terminal=false", b"Terminal=false\nDBusActivatable=true"))
        first = self.approved()
        duplicate = self.approved()
        self.assertTrue(Gio.DesktopAppInfo.new_from_filename(str(first)).get_boolean("DBusActivatable"))
        info = Gio.DesktopAppInfo.new_from_filename(str(duplicate))
        self.assertFalse(info.get_boolean("DBusActivatable"))
        self.assertEqual(info.get_string("Exec"), "/usr/bin/true %U")

    def test_pure_dbus_duplicate_returns_error_and_no_empty_file(self):
        self.write(b"[Desktop Entry]\nType=Application\nName=Pure DBus\nDBusActivatable=true\n")
        self.approved()
        with self.assertRaises(ShortcutError):
            self.approved()
        self.assertEqual(len(list(self.desktop.iterdir())), 1)

    def test_xdg_directory_is_used_without_desktop_name_assumption(self):
        self.desktop_patch.stop()
        with mock.patch("iconsend.core.GLib.get_user_special_dir", return_value=str(self.desktop)):
            self.assertEqual(desktop_directory(), self.desktop)
        self.desktop_patch.start()

    def test_disabled_or_unsafe_desktop_is_rejected(self):
        self.desktop_patch.stop()
        for value in (None, str(Path.home())):
            with mock.patch("iconsend.core.GLib.get_user_special_dir", return_value=value):
                with self.assertRaises(ShortcutError):
                    desktop_directory()
        self.desktop.chmod(0o777)
        with mock.patch("iconsend.core.GLib.get_user_special_dir", return_value=str(self.desktop)):
            with self.assertRaises(ShortcutError):
                desktop_directory()
        self.desktop_patch.start()


if __name__ == "__main__":
    unittest.main()
