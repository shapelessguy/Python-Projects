import json
import winreg
import threading
from functions.audio import *
from functions.monitors import *
from functions.generic import *
from functions.application import *
from functions.arduino import *
from utils import find_process_by_exe, Application, ERR_FLAG, PREFERENCES_PATH, DEFAULT_PREFERENCES
from utils import KEYBOARD_HOTKEYS_EXE, RVX_EXE_PATH, XM4_EXE_PATH, pprint


reg_path = "CyanHotkey"


class HandleFunction:
    def __init__(self, function_):
        self.function_ = function_
    
    def add_signal(self, signal):
        self.signal = signal
    
    def _run(self, verbose, args=()):
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
    
    def run(self, args=()):
        return self._run(False, args)
    
    def run_verbose(self, args=()):
        return self._run(True, args)
    
    def __name__(self):
        return self.function_.__name__


class RegisteredFunctions:
    HEADPHONES=HandleFunction(switch_to_headphones)
    SPEAKERS=HandleFunction(switch_to_speakers)
    VOLUME_UP=HandleFunction(volume_up)
    VOLUME_DOWN=HandleFunction(volume_down)
    FIND_WINDOWS=HandleFunction(find_windows)
    GET_SCREENS=HandleFunction(get_screens)
    ORDER=HandleFunction(order)
    SNAPSHOT=HandleFunction(get_snapshot)
    WIN_SNAPSHOT=HandleFunction(get_win_snapshot)
    TURN_ON_MONITORS=HandleFunction(turn_on_monitors)
    SHUTDOWN_MONITORS=HandleFunction(shutdown_monitors)
    GET_MOUSE_POS=HandleFunction(get_mouse_position)
    GET_APPS_STATUS=HandleFunction(get_apps_status)
    STARTUP=HandleFunction(startup_applications)
    SHOW_UWP_APP_NAMES=HandleFunction(get_uwp_apps)
    SHOW_ALARM=HandleFunction(show_alarm)
    RING_ALARM=HandleFunction(ring_alarm)

    LIGHTS_ON=HandleFunction(lights_on)
    LIGHTS_OFF=HandleFunction(lights_off)
    LIGHTS_AUTO=HandleFunction(lights_auto)

    def __init__(self, signal):
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, HandleFunction):
                attr_value.add_signal(signal)


class Signal:
    kill_flag = False
    preferences: dict
    reg_functions: RegisteredFunctions
    threads: dict[str, threading.Thread]

    def __init__(self):
        self.load_preferences()
        self.threads = {}
        self.kill_flag = False
    
    def load_preferences(self):
        if os.path.exists(PREFERENCES_PATH):
            with open(PREFERENCES_PATH, "r") as file:
                self.preferences = json.load(file)
        else:
            self.preferences = DEFAULT_PREFERENCES
    
    def get_applications(self):
        applications = self.preferences["all_profiles"][self.preferences["current_profile"]]["applications"]
        return [Application(a_name, **a) for a_name, a in applications.items()]
    
    def get_restart_options(self):
        restart_opt = self.preferences["all_profiles"][self.preferences["current_profile"]]["restart"]
        return restart_opt
    
    def get_roomserver_settings(self):
        rs_settings = self.preferences["all_profiles"][self.preferences["current_profile"]]["roomserver_settings"]
        return rs_settings
    
    def get_audio_devices(self):
        devices = self.preferences["all_profiles"][self.preferences["current_profile"]]["audio_devices"]
        return devices
    
    def save_preferences(self):
        with open(PREFERENCES_PATH, "w") as file:
            json.dump(self.preferences, file, indent=4)
    
    def set_reg_functions(self, reg_functions):
        self.reg_functions = reg_functions
    
    def register_thread(self, name, target, args: tuple):
        self.threads[name] = threading.Thread(target=target, args=args)
    
    def start_threads(self):
        for name, t in self.threads.items():
            pprint(f"Starting thread: {name}")
            t.start()
    
    def kill(self):
        self.kill_flag = True
    
    def is_alive(self):
        return not self.kill_flag


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
                        v.run_verbose() if "volume" not in function_name else v.run()
                    found = True
                    break
            if not found:
                pprint("unrecognized:", v.__name__())
        except FileNotFoundError:
            pass
        wait(signal, 0.05)


def register_functions_and_hotkeys(signal: Signal):
    reg_functions = RegisteredFunctions(signal)

    hotkeys = {
        (175, 0): reg_functions.VOLUME_UP,                  # VOL+
        (174, 0): reg_functions.VOLUME_DOWN,                # VOL-
        (96, 0): reg_functions.ORDER,                       # NUMPAD0
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

        # DEBUG PURPOSE -> NUMPAD4
        # (100, 0): reg_functions.SHOW_UWP_APP_NAMES,
        (100, 0): reg_functions.STARTUP,
        # (100, 0): reg_functions.GET_APPS_STATUS,
        # (100, 0): reg_functions.FIND_WINDOWS.run_verbose,
        # (100, 0): reg_functions.GET_SCREENS.run_verbose,
    }
    hotkeys_json = {v.__name__(): { "key": k[0], "modifier": k[1] }  for k, v in hotkeys.items()}
    hotkeys_operative = {v.__name__(): v for v in hotkeys.values()}

    find_process_by_exe(KEYBOARD_HOTKEYS_EXE, kill=True, relaunch=True, args=(json.dumps(hotkeys_json), ))
    find_process_by_exe(RVX_EXE_PATH, kill=False, relaunch=True, args=())
    find_process_by_exe(XM4_EXE_PATH, kill=False, relaunch=True, args=())

    signal.set_reg_functions(reg_functions)
    signal.register_thread(name="Hotkeys", target=listen_hotkeys, args=(signal, hotkeys_operative))
