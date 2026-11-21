import keyboard
import threading
import keyring
import ctypes
from functions.audio import play_audio
from services.pc_devices.service import set_mousepad_color, set_motherboard_color


def get_snapshot(signal, verbose=False):
    """Take a screenshot (presses Ctrl+Alt+Shift+S)."""
    keyboard.press_and_release('alt+ctrl+shift+s')


def get_win_snapshot(signal, verbose=False):
    """Take a screenshot of the active window (presses Ctrl+Alt+Shift+D)."""
    keyboard.press_and_release('alt+ctrl+shift+d')


def play_pause(signal, verbose=False):
    """Play or pause the media that is playing."""
    keyboard.press_and_release('play/pause')


def next_multimedia(signal, verbose=False):
    """Go to the next track on Spotify or whatever media is playing."""
    keyboard.press_and_release('next track')


def prev_multimedia(signal, verbose=False):
    """Go to the previous track on Spotify or whatever media is playing."""
    keyboard.press_and_release('previous track')


def type_password(signal, verbose=False):
    """Type this profile's quick password where the cursor is."""
    password = keyring.get_password("CyanManager", signal.profile)
    keyboard.write(password)


def special(signal, verbose=False):
    """Play the shocking sound."""
    threading.Thread(target=play_audio, args=("shocking.mp3", 0.1)).start()


def turn_on_mousepad(signal, verbose=False):
    """Light the mousepad up in cyan."""
    print("mousepad On")
    set_mousepad_color((0, 180, 255))


def turn_off_mousepad(signal, verbose=False):
    """Turn the mousepad's light off."""
    print("mousepad Off")
    set_mousepad_color((0, 0, 0))


def turn_on_motherboard(signal, verbose=False):
    """Light the motherboard up in cyan."""
    print("motherboard On")
    set_motherboard_color((0, 180, 255))


def turn_off_motherboard(signal, verbose=False):
    """Turn the motherboard's lights off."""
    print("motherboard Off")
    set_motherboard_color((0, 0, 0))


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


pt = POINT()
def get_mouse_position(signal, verbose=False):
    """The mouse pointer's position on the screen."""
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt