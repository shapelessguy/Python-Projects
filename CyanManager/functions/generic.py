import keyboard


def get_snapshot(signal, verbose=False):
    keyboard.press_and_release('alt+ctrl+shift+s')


def get_win_snapshot(signal, verbose=False):
    keyboard.press_and_release('alt+ctrl+shift+d')
