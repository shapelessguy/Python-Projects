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


def hotkeys_setup(signal):
    """The profile's hotkeys (Signal.get_hotkeys) into a fresh KeyboardHotkeys.exe: it takes them only
    as its argument, so any change kills and relaunches it. Returns function name -> handle."""
    functions = signal.reg_functions.get_functions()
    hotkeys_json, hotkeys_operative = {}, {}
    for h in signal.get_hotkeys():
        handle = functions.get(h.get("function"))
        if handle is None:
            print(f"Hotkey for an unknown function skipped: {h}")
            continue
        funct_name = handle.__name__()
        hotkeys_json.setdefault(funct_name, []).append({"key": int(h["key"]), "modifier": int(h.get("modifiers", 0))})
        hotkeys_operative[funct_name] = handle

    find_process_by_exe(KEYBOARD_HOTKEYS_EXE, kill=True, relaunch=True, args=(json.dumps(hotkeys_json), ))
    return hotkeys_operative


def entrypoint(thread_manager):
    signal = thread_manager.signal
    version = signal.hotkeys_version
    hotkeys_operative = hotkeys_setup(signal)

    while signal.is_alive() and not thread_manager.to_kill:
        if signal.hotkeys_version != version:  # edited from the page
            version = signal.hotkeys_version
            print("Hotkeys changed: restarting the keyboard hotkeys")
            hotkeys_operative = hotkeys_setup(signal)

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

            function_name, repetition = value.rsplit("x", 1)  # a name may have an x in it
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
                print("unrecognized:", function_name)
        except FileNotFoundError:
            pass
        wait(signal, 0.05)
    find_process_by_exe(KEYBOARD_HOTKEYS_EXE, kill=True, relaunch=False)
    print(f"{thread_manager.name} thread down..")
