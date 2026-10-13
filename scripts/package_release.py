#!/usr/bin/python3
"""Build deterministic source archives from an explicit project allowlist."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from iconsend import __version__

ROOT_FILES = (".gitignore", "README.md", "LICENSE", "CHANGELOG.md", "install.sh", "uninstall.sh", "launch.py")


def source_files():
    paths = [SOURCE / name for name in ROOT_FILES]
    for directory in ("iconsend", "nautilus", "scripts", "tests"):
        paths.extend(sorted((SOURCE / directory).glob("*.py")))
    for pattern in ("*.md", "*.json"):
        paths.extend(sorted((SOURCE / "docs").glob(pattern)))
    result = []
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Not a regular project source file: {path}")
        relative = path.relative_to(SOURCE)
        mode = 0o755 if relative.name in ("install.sh", "uninstall.sh", "launch.py") else 0o644
        result.append((relative.as_posix(), path.read_bytes(), mode))
    return result


def build(output=None):
    output = Path(output) if output else SOURCE / "dist"
    output.mkdir(parents=True, exist_ok=True)
    prefix = f"Ubuntu_iconsend-{__version__}"
    files = source_files()
    zip_path = output / f"{prefix}.zip"
    tar_path = output / f"{prefix}.tar.gz"
    checksum_path = output / "SHA256SUMS.txt"
    # A repeat build must not silently replace unrelated files.
    for destination in (zip_path, tar_path, checksum_path):
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Output already exists; choose an empty output directory: {destination}")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data, mode in files:
            info = zipfile.ZipInfo(f"{prefix}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    with tar_path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data, mode in files:
                    info = tarfile.TarInfo(f"{prefix}/{name}")
                    info.size = len(data)
                    info.mode = mode
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(data))
    checksum_path.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                                     for path in (zip_path, tar_path)), encoding="utf-8")
    return zip_path, tar_path, checksum_path


def main():
    parser = argparse.ArgumentParser(description="Build Ubuntu_iconsend source release assets")
    parser.add_argument("--output", type=Path, help="An empty output directory (default: dist/)")
    args = parser.parse_args()
    try:
        for path in build(args.output):
            print(path)
        return 0
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
