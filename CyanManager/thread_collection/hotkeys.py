import json
import winreg
import threading
from functions.audio import *
from functions.monitors import *
from functions.generic import *
from functions.application import *
from functions.arduino import *
from utils import find_process_by_exe, KEYBOARD_HOTKEYS_EXE


NAME = "Hotkeys"
PARAMETERS = {}
reg_path = "CyanHotkey"


def hotkeys_setup(signal):
    reg_functions = signal.reg_functions

    hotkeys = {
        (175, 0): reg_functions.VOLUME_UP,                  # VOL+
        (174, 0): reg_functions.VOLUME_DOWN,                # VOL-
        (96, 0): reg_functions.ORDER,                       # NUMPAD0
        (112, 0): reg_functions.ORDER,                      # F1
        (97, 0): reg_functions.HEADPHONES,                  # NUMPAD1
        (99, 0): reg_functions.SPEAKERS,                    # NUMPAD3
        (105, 0): reg_functions.SNAPSHOT,                   # NUMPAD9
        (105, 2): reg_functions.WIN_SNAPSHOT,               # CTRL + NUMPAD9
        (104, 0): reg_functions.TURN_ON_MONITORS,           # NUMPAD8
        (98, 0): reg_functions.SHUTDOWN_MONITORS,           # NUMPAD2
        (109, 0): reg_functions.SHOW_ALARM,                 # NUMPAD -
        (103, 0): reg_functions.TYPE_PASSWORD,              # NUMPAD7
        (109, 2): reg_functions.SPECIAL,                    # CTRL + NUMPAD-

        (97, 2): reg_functions.LIGHTS_ON,                   # CTRL + NUMPAD1
        (98, 2): reg_functions.LIGHTS_OFF,                  # CTRL + NUMPAD2
        (99, 2): reg_functions.LIGHTS_AUTO,                 # CTRL + NUMPAD3
        (102, 0): reg_functions.AUDIO_POWER,                # NUMPAD6
        (102, 2): reg_functions.TV_POWER,                   # CTRL + NUMPAD6
        (102, 1): reg_functions.TV_OK,                      # ALT + NUMPAD6

        # DEBUG PURPOSE
        # (100, 0): reg_functions.DISCOVER_WIN,
        # (100, 0): reg_functions.GET_WIN_POSITIONS,
        # (100, 0): reg_functions.FIND_WINDOWS,
        # (100, 0): reg_functions.SHOW_UWP_APP_NAMES,
        # (100, 0): reg_functions.THREADS_STATUS,
        # (100, 0): reg_functions.STARTUP,
        # (100, 0): reg_functions.GET_APPS_STATUS,
        # (100, 0): reg_functions.FIND_WINDOWS,
        # (100, 0): reg_functions.GET_SCREENS,
    }

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
