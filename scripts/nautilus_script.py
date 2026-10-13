#!/usr/bin/python3
"""Nautilus Scripts fallback; URI parsing preserves spaces and Unicode."""

import os
import sys
from pathlib import Path

from gi.repository import Gio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iconsend.__main__ import main

uris = os.environ.get("NAUTILUS_SCRIPT_SELECTED_URIS", "").splitlines()
paths = [Gio.File.new_for_uri(uri).get_path() for uri in uris if uri]
if not paths:
    paths = sys.argv[1:]
raise SystemExit(main(["--send-files", *(path for path in paths if path)]) if any(paths) else main())
