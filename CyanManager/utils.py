import os
import threading
import time
import keyboard


DOCUMENTS_PATH = os.path.join(os.path.expanduser("~"), "Documents")
CODEBASE_PATH = os.path.join(DOCUMENTS_PATH, "codebase")
APP_DATA_PATH = os.path.dirname(os.environ.get("APPDATA", "C:\\Users\\Default\\AppData\\Roaming"))
C_DRIVE_PATH = os.path.splitdrive(os.environ.get("ProgramFiles", "C:\\Program Files"))[0]
PROGRAM_FILES_X86_PATH = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
PROGRAM_FILES_PATH = os.environ.get("ProgramFiles", "C:\\Program Files")
SV_EXE_PATH = os.path.join(os.path.dirname(__file__), 'tools', 'svcl.exe')
ICONS_FOLDER_PATH = os.path.join(os.path.dirname(__file__), 'icons')
MULTIMONITOR_FOLDER_PATH = os.path.join(os.path.dirname(__file__), "tools", "MultiMonitorTool")
MULTIMONITOR_EXE_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "MultiMonitorTool.exe")
TEMP_MONITOR_CONF_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "temp_config.cfg")
MONITOR_CONF_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "config.cfg")
PREFERENCES_PATH = os.path.join(os.path.dirname(__file__), 'preferences.json')
ERR_FLAG = "CyanManagerError"
DEFAULT_PREFERENCES = {
    "current_profile": "default",
    "all_profiles": {
        "default": {}
    }
}


class Application:
    def __init__(self, name, window_kw, proc_name, path, arguments="", startup=False):
        self.name = name
        self.window_kw = window_kw
        self.proc_name = proc_name
        self.path = path
        self.arguments = arguments
        self.startup = startup

    def __repr__(self):
        return f"Application(name={self.name}, startup={self.startup})"


class KeyEventHolder:
    current_combination = ""
    main_thread = None
    sub_thread = None
    stop_flag = False
    modifiers = set()
    last_hotkey = ()

    def __init__(self, signal, hotkeys, blocking_hotkeys, verbose=True):
        self.signal = signal
        self.hotkeys = hotkeys
        self.blocking_hotkeys = blocking_hotkeys
        self.verbose = verbose
        self.listen()
        self.set_hotkeys()
    
    def set_comb(self, combination):
        self.current_combination = combination

    def on_key(self, event):
        name = event.name
        if name in ("shift", "ctrl", "alt", "alt gr", "cmd", "right shift", "left windows"):
            event_id = f"{event.name}-_-_-{event.scan_code}"
            if event.event_type == "down":
                self.modifiers.add(event_id)
            else:
                self.modifiers.discard(event_id)
        else:
            final = ""
            hotkey = []
            for m in sorted(self.modifiers):
                name, scan_code = m.split("-_-_-")
                final += f"  MOD {name} ({scan_code})"
                hotkey.append(name)
            final += f" - Key {event.name} ({event.scan_code} -> {event.event_type})"
            hotkey.append(event.scan_code)
            self.last_hotkey = tuple(hotkey)
            if self.verbose:
                print(final + "\n\t" + "-> HOTKEY: " + str(self.last_hotkey))
    
    def create_hook(self):
        keyboard.hook(self.on_key)
        while self.signal.is_alive() and not self.stop_flag:
            time.sleep(0.1)
        self.stop_flag = False
    
    def create_hotkeys(self):
        for keys, action in self.hotkeys.items():
            keyboard.add_hotkey(hotkey=keys, callback=action, suppress=False)
        for keys, action in self.blocking_hotkeys.items():
            keyboard.add_hotkey(hotkey=keys, callback=action, suppress=True)

        while self.signal.is_alive() and not self.stop_flag:
            time.sleep(0.1)
        self.stop_flag = False

    def listen(self):
        self.sub_thread = threading.Thread(target=self.create_hook)
        self.sub_thread.start()

    def set_hotkeys(self):
        self.main_thread = threading.Thread(target=self.create_hotkeys)
        self.main_thread.start()

    def stop(self):
        self.stop_flag = True


class Monitor_:
    def __init__(self, screen, device_name, width, height, x, y):
        self.screen = screen
        self.device_name = device_name
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.id = None
    
    def __str__(self):
        output = f"Screen {self.device_name}: "
        output += f"{self.x}:{self.y} {self.width}x{self.height} - {self.id}"
        return output
