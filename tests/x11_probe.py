"""Optional X11 end-to-end probe. Only used explicitly on the target desktop.

Uses existing libX11/libXtst rather than installing automation packages.
Does not modify display modes, refresh rates, GNOME settings or application data.
"""

import ctypes as C
import ctypes.util
import time


class ClientData(C.Union):
    _fields_ = [("b", C.c_char * 20), ("s", C.c_short * 10), ("l", C.c_long * 5)]


class ClientMessage(C.Structure):
    _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                ("display", C.c_void_p), ("window", C.c_ulong), ("message_type", C.c_ulong),
                ("format", C.c_int), ("data", ClientData)]


class Event(C.Union):
    _fields_ = [("xclient", ClientMessage), ("pad", C.c_long * 24)]


class X11:
    def __init__(self):
        self.x = C.CDLL(ctypes.util.find_library("X11"))
        self.xtst = C.CDLL(ctypes.util.find_library("Xtst"))
        self.x.XOpenDisplay.argtypes = [C.c_char_p]
        self.x.XOpenDisplay.restype = C.c_void_p
        self.x.XDefaultRootWindow.argtypes = [C.c_void_p]
        self.x.XDefaultRootWindow.restype = C.c_ulong
        self.x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
        self.x.XInternAtom.restype = C.c_ulong
        self.x.XStringToKeysym.argtypes = [C.c_char_p]
        self.x.XStringToKeysym.restype = C.c_ulong
        self.x.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]
        self.x.XKeysymToKeycode.restype = C.c_uint
        self.x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long, C.c_int, C.c_ulong,
                                              C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                              C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)]
        self.x.XFree.argtypes = [C.c_void_p]
        self.x.XFlush.argtypes = [C.c_void_p]
        self.x.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)]
        self.xtst.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
        self.xtst.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        self.xtst.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        self.x.XCloseDisplay.argtypes = [C.c_void_p]
        self.x.XTranslateCoordinates.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int,
                                                 C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_ulong)]
        self.display = self.x.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("No X11 display")
        self.root = self.x.XDefaultRootWindow(self.display)

    def atom(self, name):
        return self.x.XInternAtom(self.display, name.encode(), False)

    def origin(self, window):
        x = C.c_int()
        y = C.c_int()
        child = C.c_ulong()
        self.x.XTranslateCoordinates(self.display, window, self.root, 0, 0,
                                     C.byref(x), C.byref(y), C.byref(child))
        return x.value, y.value

    def property(self, window, name):
        actual = C.c_ulong()
        fmt = C.c_int()
        count = C.c_ulong()
        remaining = C.c_ulong()
        data = C.c_void_p()
        status = self.x.XGetWindowProperty(self.display, window, self.atom(name), 0, 4096, False, 0,
                                          C.byref(actual), C.byref(fmt), C.byref(count), C.byref(remaining), C.byref(data))
        if status or not data:
            return None
        try:
            if fmt.value == 32:
                return list(C.cast(data, C.POINTER(C.c_ulong * count.value)).contents)
            return C.string_at(data, count.value).decode("utf-8", "replace")
        finally:
            self.x.XFree(data)

    def windows(self):
        result = []
        for window in self.property(self.root, "_NET_CLIENT_LIST") or []:
            result.append({"id": window, "name": self.property(window, "_NET_WM_NAME"),
                           "class": self.property(window, "WM_CLASS"), "pid": self.property(window, "_NET_WM_PID")})
        return result

    def send(self, name, window, values):
        event = Event()
        event.xclient.type = 33
        event.xclient.display = self.display
        event.xclient.window = window
        event.xclient.message_type = self.atom(name)
        event.xclient.format = 32
        for i, value in enumerate(values):
            event.xclient.data.l[i] = value
        self.x.XSendEvent(self.display, self.root, False, (1 << 19) | (1 << 20), C.byref(event))
        self.x.XFlush(self.display)

    def show_desktop(self, value):
        self.send("_NET_SHOWING_DESKTOP", self.root, [int(value)])
        time.sleep(0.35)

    def click(self, x, y, button=1):
        self.xtst.XTestFakeMotionEvent(self.display, -1, int(x), int(y), 0)
        self.xtst.XTestFakeButtonEvent(self.display, button, True, 0)
        self.xtst.XTestFakeButtonEvent(self.display, button, False, 0)
        self.x.XFlush(self.display)

    def double_click(self, x, y):
        self.click(x, y)
        time.sleep(0.08)
        self.click(x, y)

    def close_window(self, window):
        self.send("_NET_CLOSE_WINDOW", window, [0, 2])

    def key(self, name):
        code = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(name.encode()))
        if not code:
            raise RuntimeError("Unknown key: " + name)
        self.xtst.XTestFakeKeyEvent(self.display, code, True, 0)
        self.xtst.XTestFakeKeyEvent(self.display, code, False, 0)
        self.x.XFlush(self.display)

    def close(self):
        self.x.XCloseDisplay(self.display)


if __name__ == "__main__":
    import json
    x11 = X11()
    print(json.dumps(x11.windows(), ensure_ascii=False, indent=2))
    x11.close()
