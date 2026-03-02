import keyboard
import threading
import keyring
import ctypes
from functions.audio import play_audio
from thread_collection.leds import set_mousepad_color


def get_snapshot(signal, verbose=False):
    keyboard.press_and_release('alt+ctrl+shift+s')


def get_win_snapshot(signal, verbose=False):
    keyboard.press_and_release('alt+ctrl+shift+d')


def play_pause(signal, verbose=False):
    keyboard.press_and_release('play/pause')


def next_multimedia(signal, verbose=False):
    keyboard.press_and_release('next track')


def prev_multimedia(signal, verbose=False):
    keyboard.press_and_release('previous track')


def type_password(signal, verbose=False):
    password = keyring.get_password("CyanManager", signal.profile)
    keyboard.write(password)


def special(signal, verbose=False):
    threading.Thread(target=play_audio, args=("shocking.mp3", 0.1)).start()


def turn_on_mousepad(signal, verbose=False):
    set_mousepad_color((0, 255, 255))


def turn_off_mousepad(signal, verbose=False):
    set_mousepad_color((0, 0, 0))


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


pt = POINT()
def get_mouse_position(signal, verbose=False):
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt