"""Pointer-event regression tests: a real click must create exactly one file."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from iconsend.core import list_applications

X11_SESSION = bool(os.environ.get("DISPLAY")) and os.environ.get("XDG_SESSION_TYPE") == "x11"

if X11_SESSION:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11, GLib, Gtk
    from iconsend.gui import Application, MainWindow
    from x11_probe import X11


@unittest.skipUnless(X11_SESSION, "Real pointer tests require an X11 desktop session")
class PointerCreationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application()
        cls.app.register(None)
        records = [record for record in list_applications() if record.trusted]
        if not records:
            raise unittest.SkipTest("No trusted installed application for the GUI test")
        cls.record = next((r for r in records if r.app_id == "org.gnome.Calculator.desktop"), records[0])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iconsend-pointer-")
        self.desktop = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(mock.patch.stopall)
        mock.patch("iconsend.gui.list_applications", return_value=[self.record]).start()
        mock.patch("iconsend.core.desktop_directory", return_value=self.desktop).start()
        # Count actual files without persisting test metadata in GVfs.
        mock.patch("iconsend.core.set_trusted").start()
        self.window = MainWindow(self.app)
        self.window.set_title("Ubuntu_iconsend pointer regression test")
        self.addCleanup(self.window.close)
        self.window.present()
        self.x11 = X11()
        self.addCleanup(self.x11.close)
        self.pump(650)
        self.button = next(widget for widget in self.descendants(self.window.rows[0])
                           if isinstance(widget, Gtk.Button) and widget.get_icon_name() == "list-add-symbolic")

    @staticmethod
    def descendants(widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from PointerCreationTests.descendants(child)
            child = child.get_next_sibling()

    @staticmethod
    def pump(milliseconds):
        loop = GLib.MainLoop()

        def finish():
            loop.quit()
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(milliseconds, finish)
        loop.run()

    def click(self, widget, x_fraction=0.5):
        ok, rect = widget.compute_bounds(self.window)
        self.assertTrue(ok)
        x, y = self.x11.origin(self.window.get_surface().get_xid())
        tx, ty = self.window.get_surface_transform()
        self.x11.click(x + tx + rect.get_x() + rect.get_width() * x_fraction,
                       y + ty + rect.get_y() + rect.get_height() / 2)
        self.pump(550)

    def test_one_pointer_click_creates_one_shortcut(self):
        self.click(self.button)
        self.assertEqual(len(list(self.desktop.glob("*.desktop"))), 1)

    def test_two_separate_clicks_create_two_non_overwriting_shortcuts(self):
        self.click(self.button)
        self.assertEqual(len(list(self.desktop.glob("*.desktop"))), 1)
        self.click(self.button)
        shortcuts = list(self.desktop.glob("*.desktop"))
        self.assertEqual(len(shortcuts), 2)
        self.assertEqual(len({path.name for path in shortcuts}), 2)

    def test_clicking_the_application_label_does_not_create_a_shortcut(self):
        self.click(self.window.rows[0], x_fraction=0.3)
        self.assertEqual(list(self.desktop.iterdir()), [])
