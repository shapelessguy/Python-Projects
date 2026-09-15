import ctypes
import mouse
import keyboard
import pywinctl as pwc
from screeninfo import get_monitors


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]


def _send_mouse_event(flags):
    extra = ctypes.c_ulong(0)
    inp = INPUT(type=0, mi=MOUSEINPUT(0, 0, 0, flags, 0, ctypes.pointer(extra)))
    ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


def move_relative(dx, dy):
    mouse.move(dx, dy, absolute=False, duration=0)


def click(button="left"):
    # mouse.click() uses the legacy mouse_event() API, which can silently fail
    # to register as a real click (no exception, but the target window never
    # gets focus) -- SendInput is the modern, reliable equivalent.
    down, up = (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left" else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    _send_mouse_event(down)
    _send_mouse_event(up)


def scroll(dy):
    mouse.wheel(dy)


def type_text(insert="", delete=0):
    for _ in range(max(0, delete)):
        keyboard.press_and_release("backspace")
    if insert:
        keyboard.write(insert)


def press_key(key):
    if key:
        keyboard.press_and_release(key)


def _monitor_index_for_window(win, monitors):
    cx = win.left + win.width / 2
    cy = win.top + win.height / 2
    for i, m in enumerate(monitors):
        if m.x <= cx <= m.x + m.width and m.y <= cy <= m.y + m.height:
            return i
    return 0


def _move_window_to_adjacent_monitor(step):
    win = pwc.getActiveWindow()
    if not win:
        return
    monitors = sorted(get_monitors(), key=lambda m: m.x)
    if len(monitors) < 2:
        return
    idx = _monitor_index_for_window(win, monitors)
    current = monitors[idx]
    target = monitors[(idx + step) % len(monitors)]
    was_maximized = win.isMaximized
    if was_maximized:
        win.restore()
    win.moveTo(win.left + (target.x - current.x), win.top + (target.y - current.y))
    if was_maximized:
        win.maximize()


def move_window_left():
    _move_window_to_adjacent_monitor(-1)


def move_window_right():
    _move_window_to_adjacent_monitor(1)


def toggle_maximize_window():
    win = pwc.getActiveWindow()
    if not win:
        return
    if win.isMaximized:
        win.restore()
    else:
        win.maximize()
