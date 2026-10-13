"""Validate installed launchers and create exclusively owned desktop copies.

No shell is used to interpret Exec. Trust is based on provenance/permissions or
explicit approval of the exact bytes, never just a .desktop suffix or AppInfo ID.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from .i18n import tr

GROUP = "Desktop Entry"
MAX_BYTES = 2 * 1024 * 1024


class ShortcutError(Exception):
    """An actionable failure safe to display to the user."""


class ReviewRequired(ShortcutError):
    def __init__(self, record: "ApplicationRecord"):
        self.record = record
        super().__init__(tr("Review this launcher's source and command first.", "请先检查此启动文件的来源和命令。"))


@dataclass(frozen=True)
class ApplicationRecord:
    app_id: str
    name: str
    source: Path
    info: Gio.DesktopAppInfo
    digest: str
    trusted: bool
    origin: str
    command: str


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def extend_search_path() -> None:
    """Only changes this process; call before Gio first enumerates applications."""
    dirs = [p for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if p.startswith("/")]
    for path in (
        Path.home() / ".local/share/flatpak/exports/share",
        Path("/var/lib/flatpak/exports/share"),
        Path("/var/lib/snapd/desktop"),
    ):
        if (path / "applications").is_dir() and str(path) not in dirs:
            dirs.append(str(path))
    os.environ["XDG_DATA_DIRS"] = ":".join(dirs)


def _read_source(path: Path) -> bytes:
    try:
        resolved = path.resolve(strict=True)
        fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise ShortcutError(tr("The launcher is not a regular file or is too large.", "启动文件不是普通文件，或文件过大。"))
            if before.st_uid not in (0, os.getuid()) or before.st_mode & 0o022:
                raise ShortcutError(tr("The launcher has unsafe ownership or write permissions.", "启动文件的所有者或写入权限不安全。"))
            data = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
            if len(data) > MAX_BYTES or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ShortcutError(tr("The launcher changed while it was being read; try again.", "读取过程中启动文件发生变化，请重试。"))
            return data
    except OSError as error:
        raise ShortcutError(tr("Cannot read launcher: ", "无法读取启动文件：") + str(error)) from error


def _keyfile(data: bytes) -> GLib.KeyFile:
    try:
        text = data.decode("utf-8")
        if "\x00" in text:
            raise ValueError("NUL in desktop entry")
        key = GLib.KeyFile()
        key.load_from_data(text, len(data), GLib.KeyFileFlags.KEEP_COMMENTS | GLib.KeyFileFlags.KEEP_TRANSLATIONS)
        if key.get_string(GROUP, "Type") != "Application":
            raise ValueError("Type must be Application")
        if not key.get_string(GROUP, "Name").strip():
            raise ValueError("Name is empty")
        if "Hidden" in key.get_keys(GROUP)[0] and key.get_boolean(GROUP, "Hidden"):
            raise ValueError("Hidden=true")
        return key
    except (GLib.Error, UnicodeError, ValueError) as error:
        raise ShortcutError(tr("Invalid application launcher: ", "应用启动文件无效：") + str(error)) from error


def _root_owned_chain(path: Path) -> bool:
    """Check symlink destination as well as the lexical directory chain."""
    try:
        for candidate in (path, path.resolve(strict=True)):
            for parent in (candidate, *candidate.parents):
                attrs = parent.stat()
                if attrs.st_uid != 0 or attrs.st_mode & 0o022:
                    return False
        return True
    except OSError:
        return False


def _provenance(source: Path) -> tuple[bool, str]:
    system_roots = [Path("/usr/share/applications"), Path("/usr/local/share/applications"),
                    Path("/var/lib/snapd/desktop/applications"), Path("/var/lib/flatpak/exports/share/applications")]
    system_roots += [Path(p) / "applications" for p in GLib.get_system_data_dirs() if p.startswith("/")]
    if any(_under(source, root) for root in system_roots) and _root_owned_chain(source):
        if _under(source, Path("/var/lib/snapd")):
            return True, "Snap"
        if _under(source, Path("/var/lib/flatpak")):
            return True, "Flatpak"
        return True, tr("System application", "系统应用")
    # Existing trust is accepted only for owned files in the user's app registry.
    user_root = Path(GLib.get_user_data_dir()) / "applications"
    if _under(source, user_root):
        try:
            attrs = source.stat()
            info = Gio.File.new_for_path(str(source)).query_info("metadata::trusted", Gio.FileQueryInfoFlags.NONE, None)
            parents_safe = all(p.stat().st_uid in (0, os.getuid()) and not p.stat().st_mode & 0o022 for p in (source.parent, *source.parent.parents))
            if attrs.st_uid == os.getuid() and parents_safe and info.get_attribute_as_string("metadata::trusted") == "true":
                return True, tr("Trusted user application", "已信任的用户应用")
        except (OSError, GLib.Error):
            pass
    return False, tr("User supplied — review required", "用户提供，需检查来源")


def inspect_launcher(filename: str | Path, app_id: str | None = None) -> ApplicationRecord:
    source = Path(os.path.abspath(os.fspath(filename)))
    if source.suffix != ".desktop":
        raise ShortcutError(tr("Select an application .desktop file.", "请选择应用程序的 .desktop 启动文件。"))
    data = _read_source(source)
    key = _keyfile(data)
    # Gio also checks executable availability and TryExec. Use the in-memory
    # snapshot so the preview and the digest describe the same bytes.
    try:
        info = Gio.DesktopAppInfo.new_from_keyfile(key)
    except (TypeError, GLib.Error):
        info = None
    if info is None:
        raise ShortcutError(tr("The launcher cannot be loaded. Check Exec/TryExec and whether the application is installed.", "启动文件无法加载，请检查 Exec/TryExec，以及应用是否已安装。"))
    command = info.get_string("Exec") or ""
    if not command and not info.get_boolean("DBusActivatable"):
        raise ShortcutError(tr("The launcher has no launch command.", "启动文件没有启动命令。"))
    trusted, origin = _provenance(source)
    return ApplicationRecord(app_id or source.name, info.get_display_name(), source, info,
                             hashlib.sha256(data).hexdigest(), trusted, origin, command)


def list_applications() -> list[ApplicationRecord]:
    extend_search_path()
    records = []
    for app in Gio.AppInfo.get_all():
        if not isinstance(app, Gio.DesktopAppInfo) or not app.should_show() or not app.get_filename():
            continue
        try:
            records.append(inspect_launcher(app.get_filename(), app.get_id()))
        except ShortcutError:
            continue
    return sorted(records, key=lambda app: (app.name.casefold(), app.app_id))


def desktop_directory() -> Path:
    directory = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
    if not directory:
        raise ShortcutError(tr("No XDG desktop directory is configured.", "未配置 XDG 桌面目录。"))
    path = Path(directory)
    if path == Path.home():
        raise ShortcutError(tr("The XDG desktop directory is disabled (points to Home).", "XDG 桌面目录已禁用（指向主目录）。"))
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = path.resolve(strict=True)
        attrs = path.stat()
        if not stat.S_ISDIR(attrs.st_mode) or attrs.st_uid != os.getuid() or attrs.st_mode & 0o022:
            raise ShortcutError(tr("The desktop directory has unsafe ownership or write permissions.", "桌面目录的所有者或写入权限不安全。"))
        return path
    except OSError as error:
        raise ShortcutError(tr("Cannot access the desktop directory: ", "无法访问桌面目录：") + str(error)) from error


def set_trusted(path: Path) -> None:
    file = Gio.File.new_for_path(str(path))
    try:
        if not file.set_attribute_string("metadata::trusted", "true", Gio.FileQueryInfoFlags.NONE, None):
            raise ShortcutError(tr("The desktop trust attribute could not be set.", "无法设置桌面信任属性。"))
        info = file.query_info("metadata::trusted,access::can-execute,unix::mode", Gio.FileQueryInfoFlags.NONE, None)
        if info.get_attribute_as_string("metadata::trusted") != "true" or not info.get_attribute_boolean("access::can-execute"):
            raise ShortcutError(tr("The desktop launcher did not pass the trust check.", "桌面启动文件未通过信任检查。"))
    except GLib.Error as error:
        raise ShortcutError(tr("GVfs could not trust the shortcut. Run this tool in your desktop session: ", "GVfs 无法信任快捷方式，请在当前桌面会话中使用本工具：") + error.message) from error


def create_shortcut(record: ApplicationRecord, approved_digest: str | None = None) -> Path:
    """Create a fresh 0700 launcher; remove only our newly created file on failure."""
    current = inspect_launcher(record.source, record.app_id)
    if current.digest != record.digest:
        raise ShortcutError(tr("The application launcher changed; refresh the list and review it again.", "应用启动文件已改变，请刷新列表后重新检查。"))
    if not current.trusted and approved_digest != current.digest:
        raise ReviewRequired(current)
    data = _read_source(current.source)
    if hashlib.sha256(data).hexdigest() != current.digest:
        raise ShortcutError(tr("The launcher changed; try again.", "启动文件发生变化，请重试。"))
    desktop = desktop_directory()
    try:
        directory_fd = os.open(desktop, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as error:
        raise ShortcutError(tr("Cannot open the desktop directory: ", "无法打开桌面目录：") + str(error)) from error
    filename = None
    inode = None
    try:
        for index in range(1, 10001):
            filename = current.source.name if index == 1 else f"{current.source.stem} ({index}).desktop"
            if len(os.fsencode(filename)) > 255:
                raise ShortcutError(tr("The shortcut filename is too long.", "快捷方式文件名过长。"))
            try:
                fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
                inode = os.fstat(fd).st_ino
                break
            except FileExistsError:
                continue
        else:
            raise ShortcutError(tr("Too many duplicate shortcuts.", "同名快捷方式过多。"))
        with os.fdopen(fd, "wb") as stream:
            if index > 1 and current.info.get_boolean("DBusActivatable"):
                if not current.command:
                    raise ShortcutError(tr("This application only supports D-Bus activation; its original filename is already on the desktop.", "该应用仅支持 D-Bus 启动，其原始文件名已存在于桌面。"))
                key = _keyfile(data)
                key.set_boolean(GROUP, "DBusActivatable", False)
                data = key.to_data()[0].encode("utf-8")
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o700)
            os.fsync(stream.fileno())
        result = desktop / filename
        set_trusted(result)
        return result
    except (OSError, GLib.Error, ShortcutError) as error:
        # Never delete a pre-existing file, or a file replaced by another process.
        if filename is not None and inode is not None:
            try:
                attrs = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
                if attrs.st_ino == inode and attrs.st_uid == os.getuid():
                    os.unlink(filename, dir_fd=directory_fd)
            except OSError:
                pass
        if isinstance(error, ShortcutError):
            raise
        raise ShortcutError(tr("Could not create desktop shortcut: ", "无法创建桌面快捷方式：") + str(error)) from error
    finally:
        os.close(directory_fd)
