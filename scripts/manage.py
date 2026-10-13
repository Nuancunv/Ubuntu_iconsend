#!/usr/bin/python3
"""User installation with a manifest; no shell, sudo, or silent overwrites."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from iconsend.i18n import tr
from iconsend import __version__


class InstallError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def layout(prefix=None):
    if prefix:
        base = Path(prefix).absolute()
        data = base / "share"
        bin_dir = base / "bin"
    else:
        data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        bin_dir = Path.home() / ".local/bin"
    if not data.is_absolute():
        raise InstallError("XDG_DATA_HOME must be absolute / XDG_DATA_HOME 必须是绝对路径")
    return data, bin_dir, data / "ubuntu-iconsend"


def manifest(root):
    path = root / "install-manifest.json"
    if root.is_symlink() or path.is_symlink():
        raise InstallError("Installation path is a symlink / 安装路径是符号链接")
    if not path.exists():
        if root.exists() and any(root.iterdir()):
            raise InstallError("Installation directory is already occupied / 安装目录已被其他文件占用")
        return {"files": {}}
    try:
        result = json.loads(path.read_text())
        if result.get("project") != "Ubuntu_iconsend":
            raise ValueError("wrong project")
        return result
    except (OSError, ValueError) as error:
        raise InstallError("Invalid install manifest / 安装清单无效") from error


def desktop_exec(path):
    # Desktop Entry quoting is different from shell quoting: escape percent
    # field codes and the four characters special inside double quotes.
    text = str(path).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        text = text.replace(char, "\\" + char)
    # One additional escape layer is consumed by Desktop Entry string parsing.
    return '"' + text.replace("\\", "\\\\") + '"'


def planned_files(data, bin_dir, root):
    plan = {}
    for parent in ("iconsend", "scripts", "nautilus"):
        for path in sorted((SOURCE / parent).glob("*.py")):
            plan[root / parent / path.name] = (path.read_bytes(), 0o644)
    for path in sorted((SOURCE / "docs").iterdir()):
        if path.is_file() and path.suffix in (".md", ".json"):
            plan[root / "docs" / path.name] = (path.read_bytes(), 0o644)
    plan[root / "launch.py"] = ((SOURCE / "launch.py").read_bytes(), 0o755)
    for filename in ("README.md", "LICENSE", "CHANGELOG.md", "install.sh", "uninstall.sh"):
        plan[root / filename] = ((SOURCE / filename).read_bytes(), 0o755 if filename.endswith(".sh") else 0o644)
    plan[data / "nautilus-python/extensions/iconsend_nautilus.py"] = ((SOURCE / "nautilus/iconsend_nautilus.py").read_bytes(), 0o644)
    script_name = tr("Send Shortcut to Desktop", "发送快捷方式到桌面")
    script = "#!/bin/sh\n# Ubuntu_iconsend managed file\nexec /usr/bin/python3 " + shlex.quote(str(root / "scripts/nautilus_script.py")) + ' "$@"\n'
    plan[data / "nautilus/scripts" / script_name] = (script.encode(), 0o755)
    launcher = "#!/bin/sh\n# Ubuntu_iconsend managed file\nexec /usr/bin/python3 " + shlex.quote(str(root / "launch.py")) + ' "$@"\n'
    plan[bin_dir / "ubuntu-iconsend"] = (launcher.encode(), 0o755)
    uninstall = "#!/bin/sh\n# Ubuntu_iconsend managed file\nexec /usr/bin/python3 " + shlex.quote(str(root / "scripts/manage.py")) + ' uninstall --gui "$@"\n'
    plan[bin_dir / "ubuntu-iconsend-uninstall"] = (uninstall.encode(), 0o755)
    desktop = f"""[Desktop Entry]
Type=Application
Name=Send to Desktop
Name[zh_CN]=发送到桌面
Name[zh_TW]=傳送到桌面
Comment=Create desktop shortcuts for installed applications
Comment[zh_CN]=为已安装应用创建桌面快捷方式
Exec=/usr/bin/python3 {desktop_exec(root / 'launch.py')}
Icon=user-desktop
Terminal=false
Categories=Utility;GTK;
Keywords=desktop;shortcut;launcher;
Keywords[zh_CN]=桌面;快捷方式;启动器;
StartupNotify=true
"""
    plan[data / "applications/io.github.iconsend.UbuntuIconsEnd.desktop"] = (desktop.encode(), 0o644)
    return plan


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".iconsend-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(prefix=None):
    if os.getuid() == 0:
        raise InstallError("Run the user installer without sudo / 用户安装程序请勿使用 sudo")
    from iconsend.diagnostics import dependencies
    deps = dependencies()
    missing = [name for name in ("python3-gi", "gir1.2-gtk-4.0", "gir1.2-adw-1") if not deps[name]]
    if missing:
        raise InstallError("Missing dependencies / 缺少依赖：" + ", ".join(missing))
    data, bin_dir, root = layout(prefix)
    previous = manifest(root)
    plan = planned_files(data, bin_dir, root)
    # Check every destination before writing any files.
    for path in plan:
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or previous["files"].get(str(path)) != digest(path.read_bytes()):
                raise InstallError("Will not overwrite an existing or modified file / 不会覆盖现有或已修改文件：" + str(path))
        for parent in path.parents:
            if parent.exists() and (parent.is_symlink() or parent.stat().st_uid not in (0, os.getuid()) or parent.stat().st_mode & 0o002):
                # /tmp is allowed for isolated installation tests only.
                if not (prefix and parent == Path("/tmp")):
                    raise InstallError("Unsafe installation parent / 安装父目录不安全：" + str(parent))
    new_manifest = {"project": "Ubuntu_iconsend", "version": __version__, "files": dict(previous["files"])}
    backups = {}
    written = []
    try:
        for path, (content, mode) in plan.items():
            backups[path] = (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
            atomic_write(path, content, mode)
            written.append(path)
            new_manifest["files"][str(path)] = digest(content)
        atomic_write(root / "install-manifest.json", json.dumps(new_manifest, ensure_ascii=False, indent=2).encode(), 0o600)
    except OSError:
        for path in reversed(written):
            if backups[path] is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, *backups[path])
        for directory in sorted({p.parent for p in plan} | {root}, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    if __import__('shutil').which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(data / "applications")], capture_output=True)
    return tr("Installed. Open “Send to Desktop” in Show Applications. Nautilus loads the menu on its next start.",
              "安装完成。打开“显示应用程序”中的“发送到桌面”即可使用。Nautilus 下次启动时会加载右键菜单。")


def uninstall(prefix=None):
    data, bin_dir, root = layout(prefix)
    previous = manifest(root)
    skipped = []
    dirs = set()
    removed = []
    # Validate manifest paths against our layout, not arbitrary manifest data.
    external = {bin_dir / "ubuntu-iconsend", bin_dir / "ubuntu-iconsend-uninstall",
                data / "applications/io.github.iconsend.UbuntuIconsEnd.desktop",
                data / "nautilus-python/extensions/iconsend_nautilus.py",
                data / "nautilus/scripts/Send Shortcut to Desktop", data / "nautilus/scripts/发送快捷方式到桌面"}
    for raw, checksum in previous["files"].items():
        path = Path(raw)
        if path not in external and root not in path.parents:
            raise InstallError("Manifest contains an unexpected path / 清单包含非本项目路径：" + raw)
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != checksum:
            skipped.append(raw)
            continue
        path.unlink()
        removed.append(raw)
        dirs.add(path.parent)
    # Python cache files are ours only when their matching .py was in the manifest.
    cache_dirs = {Path(p).parent / "__pycache__" for p in previous["files"] if p.endswith(".py")}
    for cache_dir in cache_dirs:
        if cache_dir.is_dir() and not cache_dir.is_symlink():
            for file in cache_dir.glob("*.pyc"):
                module = file.name.split(".")[0] + ".py"
                if str(cache_dir.parent / module) in previous["files"] and not file.is_symlink():
                    file.unlink()
            dirs.add(cache_dir)
    if not skipped:
        (root / "install-manifest.json").unlink(missing_ok=True)
    else:
        previous["files"] = {key: value for key, value in previous["files"].items() if key in skipped}
        atomic_write(root / "install-manifest.json", json.dumps(previous, indent=2).encode(), 0o600)
    dirs.update((root / "iconsend", root / "scripts", root / "nautilus", root / "docs", root))
    for directory in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    if __import__('shutil').which("update-desktop-database") and (data / "applications").is_dir():
        subprocess.run(["update-desktop-database", str(data / "applications")], capture_output=True)
    if skipped:
        return tr("Kept modified files: ", "保留已修改文件：") + "\n" + "\n".join(skipped)
    return tr("Uninstalled. Existing desktop shortcuts and system dependencies were kept.", "卸载完成。已创建的桌面快捷方式和系统依赖已保留。")


def graphical(action, prefix=None):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib, Gtk
    app = Adw.Application(application_id="io.github.iconsend.Installer", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(_app):
        window = Adw.ApplicationWindow(application=app, title="Ubuntu_iconsend", default_width=500, default_height=360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        page = Adw.StatusPage(icon_name="user-desktop-symbolic", title=tr("Install Send to Desktop", "安装“发送到桌面”") if action == "install" else tr("Uninstall Send to Desktop", "卸载“发送到桌面”"),
                              description=tr("Install for the current user. No desktop settings will be changed.", "为当前用户安装，不更改桌面设置。") if action == "install" else tr("Remove the project's installed files. Modified files and desktop shortcuts will be kept.", "移除本项目的安装文件。保留已修改文件和桌面快捷方式。"))
        box.append(page)
        button = Gtk.Button(label=tr("Install", "安装") if action == "install" else tr("Uninstall", "卸载"), halign=Gtk.Align.CENTER)
        button.add_css_class("suggested-action" if action == "install" else "destructive-action")
        page.set_child(button)

        def perform(_button):
            try:
                message = install(prefix) if action == "install" else uninstall(prefix)
                page.set_title(tr("Complete", "完成"))
                page.set_description(message)
                button.set_label(tr("Close", "关闭"))
                button.disconnect(handler)
                button.connect("clicked", lambda _b: window.close())
            except (InstallError, OSError) as error:
                page.set_description(str(error))

        handler = button.connect("clicked", perform)
        window.set_content(box)
        window.present()

    app.connect("activate", activate)
    return app.run([])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--prefix", help="Isolated destination for testing")
    args = parser.parse_args()
    try:
        if args.gui:
            return graphical(args.action, args.prefix)
        print(install(args.prefix) if args.action == "install" else uninstall(args.prefix))
        return 0
    except (InstallError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
