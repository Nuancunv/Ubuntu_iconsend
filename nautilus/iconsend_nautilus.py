"""Thin Nautilus MenuProvider. Never load GTK or parse Exec with a shell."""

import os
import subprocess
import sys
from pathlib import Path

import gi

try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    gi.require_version("Nautilus", "3.0")
from gi.repository import Gio, GObject, Nautilus

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
ROOT = DATA_HOME / "ubuntu-iconsend"
if not (ROOT / "launch.py").is_file():
    ROOT = Path("/usr/share/ubuntu-iconsend")
sys.path.insert(0, str(ROOT))

from iconsend.core import ShortcutError, inspect_launcher
from iconsend.i18n import tr


class IconSendMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, *args):
        files = args[-1]
        if not files or not (ROOT / "launch.py").is_file():
            return []
        paths = []
        for file in files:
            if file.is_directory():
                return []
            path = Gio.File.new_for_uri(file.get_uri()).get_path()
            if not path:
                return []
            try:
                inspect_launcher(path)
            except ShortcutError:
                return []
            paths.append(path)
        item = Nautilus.MenuItem(name="IconSend::SendToDesktop",
                                 label=tr("Send Shortcut to Desktop", "发送快捷方式到桌面"),
                                 tip=tr("Create desktop shortcuts for these applications", "为这些应用创建桌面快捷方式"),
                                 icon="user-desktop")
        item.connect("activate", self.activate, paths)
        return [item]

    def activate(self, _item, paths):
        try:
            subprocess.Popen(["/usr/bin/python3", str(ROOT / "launch.py"), "--send-files", *paths],
                             cwd=str(Path.home()), start_new_session=True)
        except OSError as error:
            # Never throw into Nautilus's menu activation callback.
            print(f"Ubuntu_iconsend: {error}", file=sys.stderr)
