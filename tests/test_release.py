import hashlib
import importlib.util
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("package_release", Path(__file__).resolve().parents[1] / "scripts/package_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class SourceReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iconsend-release-")
        self.output = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_archives_match_sources_and_include_license_and_executable_installer(self):
        zip_path, tar_path, _ = release.build(self.output)
        prefix = f"Ubuntu_iconsend-{release.__version__}/"
        with zipfile.ZipFile(zip_path) as zipped, tarfile.open(tar_path, "r:gz") as tarred:
            self.assertEqual(set(zipped.namelist()), set(tarred.getnames()))
            self.assertIn(prefix + "LICENSE", zipped.namelist())
            self.assertIn(prefix + "scripts/manage.py", zipped.namelist())
            self.assertEqual(zipped.getinfo(prefix + "install.sh").external_attr >> 16 & 0o777, 0o755)
            self.assertEqual(tarred.getmember(prefix + "install.sh").mode, 0o755)
            for name, data, _mode in release.source_files():
                self.assertEqual(zipped.read(prefix + name), data)
                self.assertEqual(tarred.extractfile(prefix + name).read(), data)
            for name in zipped.namelist():
                self.assertNotIn("__pycache__", name)
                self.assertNotIn("/.git/", name)
                self.assertNotIn("/dist/", name)
                self.assertFalse(name.startswith("/"))

    def test_checksums_verify_both_archives(self):
        _zip_path, _tar_path, checksums = release.build(self.output)
        for line in checksums.read_text().splitlines():
            checksum, filename = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.output / filename).read_bytes()).hexdigest(), checksum)

    def test_build_is_reproducible(self):
        first = release.build(self.output / "first")
        second = release.build(self.output / "second")
        self.assertEqual([path.read_bytes() for path in first], [path.read_bytes() for path in second])

    def test_existing_output_is_preserved(self):
        path = self.output / f"Ubuntu_iconsend-{release.__version__}.zip"
        path.write_bytes(b"existing file")
        with self.assertRaises(FileExistsError):
            release.build(self.output)
        self.assertEqual(path.read_bytes(), b"existing file")
