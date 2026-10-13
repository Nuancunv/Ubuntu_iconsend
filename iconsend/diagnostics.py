"""Read-only diagnostics. Subprocesses have timeouts and never change settings."""

import os
import subprocess
from pathlib import Path

try:
    from gi.repository import GLib
except ImportError:
    GLib = None


def command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
        return result.stdout.strip() or result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)


def dependencies():
    results = {}
    # Different library versions must be probed in separate processes.
    for namespace, version, package in [("Gio", "2.0", "python3-gi"), ("Gtk", "4.0", "gir1.2-gtk-4.0"),
                                        ("Adw", "1", "gir1.2-adw-1"), ("Nautilus", "4.0", "python3-nautilus")]:
        script = f"import gi; gi.require_version({namespace!r}, {version!r}); from gi.repository import {namespace}"
        result = subprocess.run(["/usr/bin/python3", "-c", script], capture_output=True, text=True)
        results[package] = result.returncode == 0
    results["python3-nautilus"] = results["python3-nautilus"] and subprocess.run(
        ["dpkg-query", "-W", "-f=${db:Status-Status}", "python3-nautilus"], capture_output=True, text=True).stdout.strip() == "installed"
    return results


def report():
    release = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            release[key] = value.strip('"')
    return {
        "os": release.get("PRETTY_NAME"),
        "gnome_shell": command("gnome-shell", "--version"),
        "nautilus": command("nautilus", "--version"),
        "session": os.environ.get("XDG_SESSION_TYPE"),
        "current_desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        "desktop_directory": GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP) if GLib else None,
        "dependencies": dependencies(),
        "enabled_extensions": command("gnome-extensions", "list", "--enabled").splitlines(),
        "package_versions": command("dpkg-query", "-W", "python3-gi", "python3-nautilus", "gir1.2-gtk-4.0", "gir1.2-adw-1", "gvfs", "gvfs-daemons", "gnome-shell-extension-desktop-icons-ng"),
        "xdg_data_dirs": os.environ.get("XDG_DATA_DIRS"),
    }
