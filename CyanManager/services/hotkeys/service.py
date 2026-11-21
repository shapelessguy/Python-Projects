import os
import json
import winreg
import threading
from functions.audio import *
from functions.monitors import *
from functions.generic import *
from functions.application import *
from functions.arduino import *
from utils import find_process_by_exe


NAME = "Hotkeys"
PARAMETERS = {}
reg_path = "CyanHotkey"

KEYBOARD_HOTKEYS_EXE = os.path.join(os.path.dirname(__file__), "tools", "KeyboardHotkeys", "KeyboardHotkeys",
                                    "bin", "Release", "net10.0-windows", "KeyboardHotkeys.exe")


# (Windows virtual-key code, modifiers, registered function). Modifiers are
# RegisterHotKey's bits: 1 Alt, 2 Ctrl, 4 Shift, 8 Win. The page's keyboard
# view (Functions tab) reads this list too.
HOTKEYS = [
    (175, 0, "VOLUME_UP"),          # VOL+
    (174, 0, "VOLUME_DOWN"),        # VOL-
    (96, 0, "ORDER"),               # NUMPAD0
    (112, 0, "ORDER"),              # F1
    (97, 0, "HEADPHONES"),          # NUMPAD1
    (99, 0, "SPEAKERS"),            # NUMPAD3
    (105, 0, "SNAPSHOT"),           # NUMPAD9
    # (105, 2, "WIN_SNAPSHOT"),     # CTRL + NUMPAD9
    (104, 0, "TURN_ON_MONITORS"),   # NUMPAD8
    (98, 0, "SHUTDOWN_MONITORS"),   # NUMPAD2
    (109, 0, "SHOW_ALARM"),         # NUMPAD -
    (103, 0, "TYPE_PASSWORD"),      # NUMPAD7
    (109, 2, "SPECIAL"),            # CTRL + NUMPAD-

    (97, 2, "LIGHTS_ON"),           # CTRL + NUMPAD1
    (98, 2, "LIGHTS_OFF"),          # CTRL + NUMPAD2
    (99, 2, "LIGHTS_AUTO"),         # CTRL + NUMPAD3

    (100, 2, "TOP_RGB"),            # CTRL + NUMPAD4
    (101, 2, "TOP_COL_CHANGE"),     # CTRL + NUMPAD5
    (102, 2, "TOP_HEART"),          # CTRL + NUMPAD6
    (103, 2, "TOP_POWER"),          # CTRL + NUMPAD7
    (104, 2, "TOP_BRIGHT_MINUS"),   # CTRL + NUMPAD8
    (105, 2, "TOP_BRIGHT_PLUS"),    # CTRL + NUMPAD9

    (102, 0, "AUDIO_POWER"),        # NUMPAD6
    (102, 3, "TV_POWER"),           # CTRL + ALT + NUMPAD6
    (102, 1, "TV_OK"),              # ALT + NUMPAD6

    # DEBUG PURPOSE: DISCOVER_WIN, GET_WIN_POSITIONS, FIND_WINDOWS,
    # SHOW_UWP_APP_NAMES, THREADS_STATUS, STARTUP, GET_APPS_STATUS, GET_SCREENS
    # (100, 0, "DISCOVER_WIN"),
]


def hotkeys_setup(signal):
    reg_functions = signal.reg_functions
    hotkeys = {(key, modifier): getattr(reg_functions, name) for key, modifier, name in HOTKEYS}

    hotkeys_json, hotkeys_operative = {}, {}
    for k, v in hotkeys.items():
        funct_name = v.__name__()
        hotkeys_json[funct_name] = hotkeys_json.get(funct_name, []) + [{ "key": k[0], "modifier": k[1] }]
        hotkeys_operative[funct_name] = v

    find_process_by_exe(KEYBOARD_HOTKEYS_EXE, kill=True, relaunch=True, args=(json.dumps(hotkeys_json), ))
    return hotkeys_operative


def entrypoint(thread_manager):
    signal = thread_manager.signal
    hotkeys_operative = hotkeys_setup(signal)

    while signal.is_alive() and not thread_manager.to_kill:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "alarm")
            winreg.CloseKey(key)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path)
            if value == "ALARM":
                threading.Thread(target=signal.reg_functions.RING_ALARM.run).start()
        except FileNotFoundError:
            pass

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "function")
            winreg.CloseKey(key)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path)
            found = False

            function_name, repetition = value.split("x")
            if function_name == "sessionLocked":
                signal.session_locked = True
                found = True
            elif function_name == "sessionUnlocked":
                signal.session_locked = False
                found = True
            for k, v in hotkeys_operative.items():
                if k == function_name:
                    for _ in range(int(repetition)):
                        v.run_shortcut()
                    found = True
                    break


            if not found:
                print("unrecognized:", v.__name__())
        except FileNotFoundError:
            pass
        wait(signal, 0.05)
    find_process_by_exe(KEYBOARD_HOTKEYS_EXE, kill=True, relaunch=False)
    print(f"{thread_manager.name} thread down..")
