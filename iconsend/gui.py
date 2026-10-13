"""GTK 4/libadwaita UI, kept outside the Nautilus process."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .core import ApplicationRecord, ShortcutError, create_shortcut, desktop_directory, inspect_launcher, list_applications
from .i18n import tr

APP_ID = "io.github.iconsend.UbuntuIconsEnd"


def review(parent: Gtk.Window, record: ApplicationRecord, callback) -> None:
    dialog = Adw.MessageDialog.new(parent,
        tr("Review application launcher", "检查应用启动文件"),
        tr("The source of this launcher could not be verified. Only create a shortcut if you recognize the application and trust this command.",
           "无法验证此启动文件的安装来源。请确认你认识该应用且信任以下命令，再创建快捷方式。"))
    details = Gtk.Label(label=f"{record.name}\n\n{record.source}\n\n{record.command or 'D-Bus: ' + record.app_id}\n\nSHA-256: {record.digest}",
                        wrap=True, selectable=True, xalign=0)
    details.set_max_width_chars(65)
    dialog.set_extra_child(details)
    dialog.add_response("cancel", tr("Cancel", "取消"))
    dialog.add_response("create", tr("Trust and create", "信任并创建"))
    dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")
    dialog.connect("response", lambda _dialog, response: callback(record.digest if response == "create" else None))
    dialog.present()


def show_error(parent: Gtk.Window, error: Exception) -> None:
    dialog = Adw.MessageDialog.new(parent, tr("Could not create shortcut", "无法创建快捷方式"), str(error))
    dialog.add_response("close", tr("Close", "关闭"))
    dialog.set_close_response("close")
    dialog.present()


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=tr("Send to Desktop", "发送到桌面"), default_width=580, default_height=680)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        desktop_button = Gtk.Button(icon_name="user-desktop-symbolic", tooltip_text=tr("Open desktop folder", "打开桌面文件夹"))
        desktop_button.connect("clicked", lambda _button: self.open_desktop())
        header.pack_start(desktop_button)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=tr("Refresh applications", "刷新应用列表"))
        refresh.connect("clicked", lambda _button: self.reload())
        header.pack_end(refresh)
        box.append(header)
        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=20, margin_end=20, margin_top=8, margin_bottom=12)
        self.search = Gtk.SearchEntry(placeholder_text=tr("Search applications", "搜索应用程序"), hexpand=True)
        self.search.connect("search-changed", lambda _entry: self.filter_changed())
        search_box.append(self.search)
        self.count_label = Gtk.Label(xalign=0)
        self.count_label.add_css_class("dim-label")
        search_box.append(self.count_label)
        box.append(search_box)
        self.stack = Gtk.Stack(vexpand=True)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, margin_start=20, margin_end=20, margin_bottom=20)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_filter_func(self.row_visible)
        scroll.set_child(self.listbox)
        self.stack.add_named(scroll, "list")
        self.empty = Adw.StatusPage(icon_name="system-search-symbolic", title=tr("No applications found", "未找到应用"),
                                    description=tr("Try another search or refresh the application list.", "尝试其他关键词，或刷新应用列表。"))
        self.stack.add_named(self.empty, "empty")
        box.append(self.stack)
        self.overlay = Adw.ToastOverlay()
        self.overlay.set_child(box)
        self.set_content(self.overlay)
        self.records = []
        self.rows = []
        self.reload()
        self.search.grab_focus()

    def reload(self):
        for row in self.rows:
            self.listbox.remove(row)
        self.rows = []
        try:
            self.records = list_applications()
        except (ShortcutError, GLib.Error) as error:
            show_error(self, error)
            self.records = []
        for record in self.records:
            row = Adw.ActionRow(title=GLib.markup_escape_text(record.name), subtitle=record.origin, use_markup=True)
            row.record = record
            image = Gtk.Image.new_from_gicon(record.info.get_icon() or Gio.ThemedIcon.new("application-x-executable"))
            image.set_pixel_size(36)
            row.add_prefix(image)
            button = Gtk.Button(icon_name="list-add-symbolic", valign=Gtk.Align.CENTER,
                                tooltip_text=tr("Create shortcut for ", "创建快捷方式：") + record.name)
            button.add_css_class("flat")
            button.connect("clicked", self.clicked, record)
            row.add_suffix(button)
            # Only the + button creates a shortcut. Making the row activate the
            # same button can turn its pointer release into a second activation
            # when create() temporarily changes the button's sensitivity.
            self.listbox.append(row)
            self.rows.append(row)
        self.filter_changed()

    def row_visible(self, row):
        query = self.search.get_text().strip().casefold()
        return query in f"{row.record.name}\n{row.record.app_id}\n{row.record.info.get_description() or ''}".casefold()

    def filter_changed(self):
        self.listbox.invalidate_filter()
        visible = sum(self.row_visible(row) for row in self.rows)
        self.count_label.set_text(tr(f"{visible} applications · Click + to send to desktop", f"{visible} 个应用 · 点击 + 发送到桌面"))
        self.stack.set_visible_child_name("list" if visible else "empty")

    def clicked(self, button, record):
        # Reinspect before showing the trust preview if the app list is stale.
        try:
            record = inspect_launcher(record.source, record.app_id)
        except ShortcutError as error:
            show_error(self, error)
            return
        if record.trusted:
            self.create(button, record, None)
        else:
            review(self, record, lambda digest: self.create(button, record, digest) if digest else None)

    def create(self, button, record, digest):
        button.set_sensitive(False)
        try:
            path = create_shortcut(record, digest)
            toast = Adw.Toast.new(tr("Created: ", "已创建：") + record.name)
            toast.set_timeout(5)
            self.overlay.add_toast(toast)
            self.count_label.set_text(str(path))
        except ShortcutError as error:
            show_error(self, error)
        finally:
            button.set_sensitive(True)

    def open_desktop(self):
        try:
            Gio.AppInfo.launch_default_for_uri(desktop_directory().as_uri(), None)
        except (ShortcutError, GLib.Error) as error:
            show_error(self, error)


class SendWindow(Adw.ApplicationWindow):
    """A short result window for Nautilus operations, with review when needed."""

    def __init__(self, app, paths):
        super().__init__(application=app, title=tr("Send to Desktop", "发送到桌面"), default_width=480, default_height=360)
        self.pending = list(paths)
        self.results = []
        self.failures = []
        self.page = Adw.StatusPage(title=tr("Creating shortcuts…", "正在创建快捷方式…"), icon_name="user-desktop-symbolic")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(Adw.HeaderBar())
        box.append(self.page)
        self.set_content(box)
        GLib.idle_add(self.next_file)

    def next_file(self):
        if not self.pending:
            self.finish()
            return GLib.SOURCE_REMOVE
        filename = self.pending.pop(0)
        try:
            record = inspect_launcher(filename)
            if record.trusted:
                self.create(record, None)
            else:
                review(self, record, lambda digest: self.create(record, digest) if digest else self.cancel_file())
        except ShortcutError as error:
            self.failures.append(str(error))
            GLib.idle_add(self.next_file)
        return GLib.SOURCE_REMOVE

    def cancel_file(self):
        self.failures.append(tr("Creation cancelled.", "已取消创建。"))
        GLib.idle_add(self.next_file)

    def create(self, record, digest):
        try:
            self.results.append(create_shortcut(record, digest))
        except ShortcutError as error:
            self.failures.append(str(error))
        GLib.idle_add(self.next_file)

    def finish(self):
        self.page.set_title(tr("Shortcut created", "快捷方式已创建") if self.results and not self.failures else tr("Results", "操作结果"))
        self.page.set_icon_name("emblem-ok-symbolic" if not self.failures else "dialog-warning-symbolic")
        text = "\n".join([*(str(p) for p in self.results), *self.failures])
        self.page.set_description(text)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        close = Gtk.Button(label=tr("Close", "关闭"))
        close.connect("clicked", lambda _button: self.close())
        buttons.append(close)
        if self.results:
            open_button = Gtk.Button(label=tr("Open desktop folder", "打开桌面文件夹"))
            open_button.add_css_class("suggested-action")
            open_button.connect("clicked", self.open_desktop)
            buttons.append(open_button)
        self.page.set_child(buttons)

    def open_desktop(self, _button):
        try:
            Gio.AppInfo.launch_default_for_uri(desktop_directory().as_uri(), None)
        except (GLib.Error, ShortcutError) as error:
            show_error(self, error)


class Application(Adw.Application):
    def __init__(self, paths=None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.paths = paths

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            window = SendWindow(self, self.paths) if self.paths else MainWindow(self)
        window.present()


def run(paths=None):
    return Application(paths).run([])
