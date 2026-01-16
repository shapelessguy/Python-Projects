import json
import winreg
import threading
from functions.audio import *
from functions.monitors import *
from functions.generic import *
from functions.application import *
from functions.arduino import *
from utils import find_process_by_exe, ERR_FLAG, KEYBOARD_HOTKEYS_EXE, RVX_EXE_PATH, XM4_EXE_PATH, pprint


reg_path = "CyanHotkey"


def listen_hotkeys(signal, hotkeys_operative):
    while signal.is_alive():

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
            for k, v in hotkeys_operative.items():
                function_name, repetition = value.split("x")
                if k == function_name:
                    for _ in range(int(repetition)):
                        v.run_shortcut()
                    found = True
                    break
            if not found:
                pprint("unrecognized:", v.__name__())
        except FileNotFoundError:
            pass
        wait(signal, 0.05)


class HandleFunction:
    def __init__(self, function_, verbose_always_off=False):
        self.function_ = function_
        self.verbose_always_off = verbose_always_off
    
    def add_signal(self, signal):
        self.signal = signal
    
    def _run(self, verbose, *args):
        result = ERR_FLAG
        try:
            if verbose:
                pprint(f"RUN FUNCTION: '{self.function_.__name__}'")
            result = self.function_(self.signal, verbose, *args)
        except:
            import traceback
            text = "\n-----------------\n"
            text += traceback.format_exc()
            text += "-----------------\n"
            pprint(text)
        return result
    
    def run(self, *args):
        return self._run(False, *args)
    
    def run_shortcut(self, *args):
        self.signal.last_interaction = datetime.now()
        return self._run(not self.verbose_always_off, *args)
    
    def __name__(self):
        return self.function_.__name__


class RegisteredFunctions:
    HEADPHONES=HandleFunction(switch_to_headphones)
    SPEAKERS=HandleFunction(switch_to_speakers)
    VOLUME_UP=HandleFunction(volume_up, verbose_always_off=True)
    VOLUME_DOWN=HandleFunction(volume_down, verbose_always_off=True)
    FIND_WINDOWS=HandleFunction(find_windows)
    GET_SCREENS=HandleFunction(get_screens)
    ORDER=HandleFunction(order)
    SNAPSHOT=HandleFunction(get_snapshot)
    WIN_SNAPSHOT=HandleFunction(get_win_snapshot)
    TURN_ON_MONITORS=HandleFunction(turn_on_monitors)
    SHUTDOWN_MONITORS=HandleFunction(shutdown_monitors)
    GET_MOUSE_POS=HandleFunction(get_mouse_position)
    GET_APPS_STATUS=HandleFunction(get_apps_status)
    GET_WIN_POSITIONS=HandleFunction(get_win_pos)
    DISCOVER_WIN=HandleFunction(discover_windows)
    STARTUP=HandleFunction(startup_applications)
    KILL_APP=HandleFunction(kill_application)
    SHOW_UWP_APP_NAMES=HandleFunction(get_uwp_apps)
    SHOW_ALARM=HandleFunction(show_alarm)
    RING_ALARM=HandleFunction(ring_alarm)
    THREADS_STATUS=HandleFunction(get_threads_status)

    LIGHTS_ON=HandleFunction(lights_on)
    LIGHTS_OFF=HandleFunction(lights_off)
    LIGHTS_AUTO=HandleFunction(lights_auto)

    def __init__(self, signal):
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, HandleFunction):
                attr_value.add_signal(signal)


def register_functions_and_hotkeys(signal):
    reg_functions = RegisteredFunctions(signal)

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

        (97, 2): reg_functions.LIGHTS_ON,                   # CTRL + NUMPAD1
        (98, 2): reg_functions.LIGHTS_OFF,                  # CTRL + NUMPAD2
        (99, 2): reg_functions.LIGHTS_AUTO,                 # CTRL + NUMPAD3

        # DEBUG PURPOSE
        (100, 0): reg_functions.DISCOVER_WIN,
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
    find_process_by_exe(RVX_EXE_PATH, kill=False, relaunch=True, args=())
    find_process_by_exe(XM4_EXE_PATH, kill=False, relaunch=True, args=())

    signal.set_reg_functions(reg_functions)
    signal.register_thread(name="Hotkeys", target=listen_hotkeys, args=(signal, hotkeys_operative))
