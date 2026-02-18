import keyboard
import time
import keyring
import ctypes
from functions.audio import play_audio


def get_snapshot(signal, verbose=False):
    keyboard.press_and_release('alt+ctrl+shift+s')


def get_win_snapshot(signal, verbose=False):
    keyboard.press_and_release('alt+ctrl+shift+d')


def play_pause(signal, verbose=False):
    keyboard.press_and_release('play/pause')


def type_password(signal, verbose=False):
    password = keyring.get_password("CyanManager", signal.profile)
    keyboard.write(password)


def special(signal, verbose=False):
    play_audio("shocking.mp3")


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


pt = POINT()
def get_mouse_position(signal, verbose=False):
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt