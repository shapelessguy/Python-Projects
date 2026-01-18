import os
import psutil
import time
import subprocess
import json
from plyer import notification
from datetime import datetime


APP_DATA_PATH = os.path.dirname(os.environ.get("APPDATA", "C:/Users/Default/AppData/Roaming"))
C_DRIVE_PATH = os.path.splitdrive(os.environ.get("ProgramFiles", "C:/Program Files"))[0]
PROGRAM_FILES_X86_PATH = os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")
PROGRAM_FILES_PATH = os.environ.get("ProgramFiles", "C:/Program Files")

TOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tools')
CYANSYNC_LOGS_PATH = os.path.join(TOOLS_PATH, 'cyanSync', 'logs')
SV_EXE_PATH = os.path.join(TOOLS_PATH, 'svcl.exe')
MULTIMONITOR_FOLDER_PATH = os.path.join(TOOLS_PATH, "MultiMonitorTool")
RVX_EXE_PATH = os.path.join(TOOLS_PATH, "3RVX_portable", "3RVX.exe")
XM4_EXE_PATH = os.path.join(TOOLS_PATH, "Xm4Battery-5.11.14", "Xm4Battery", "bin", "Release", "net10.0-windows", "Xm4Battery.exe")
KEYBOARD_HOTKEYS_EXE = os.path.join(TOOLS_PATH, "KeyboardHotkeys", "KeyboardHotkeys", "bin", "Release", "net10.0-windows", "KeyboardHotkeys.exe")
TIMER_EXE = os.path.join(TOOLS_PATH, "Timer", "Timer", "bin", "Release", "net10.0-windows", "Timer.exe")
MULTIMONITOR_EXE_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "MultiMonitorTool.exe")
TEMP_MONITOR_CONF_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "temp_config.cfg")
MONITOR_CONF_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "config.cfg")

DOCUMENTS_PATH = os.path.join(os.path.expanduser("~"), "Documents")
CODEBASE_PATH = os.path.join(DOCUMENTS_PATH, "codebase")
ICONS_FOLDER_PATH = os.path.join(os.path.dirname(__file__), 'icons')
CONFIGURATIONS_PATH = os.path.join(os.path.dirname(__file__), 'configurations')
EXE_MAP_PATH = os.path.join(os.path.dirname(__file__), 'exe_map.json')
ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
ERR_FLAG = "CyanManagerError"


class Tee:
    def __init__(self, log_queue, stream):
        self.log_queue = log_queue
        self.stream = stream

    def write(self, msg):
        self.stream.write(msg)
        self.stream.flush()
        self.log_queue.put(msg)

    def flush(self):
        self.stream.flush()


def wait(signal, ms: int):
    while signal.is_alive():
        remaining = ms
        while remaining > 0 and signal.is_alive():
            time.sleep(min(remaining / 1000, 0.05))
            remaining -= 50
        break


def pprint(*args, dt_format="%Y-%m-%d %H:%M:%S", **kwargs):
    """
    Prints messages with a timestamp.
    All args are joined into a single string to avoid splitting.
    """
    timestamp = datetime.now().strftime(dt_format)
    # Join all args with spaces into one string
    message = " ".join(str(arg) for arg in args)
    print(f"[{timestamp}] {message}", **kwargs, flush=True)


def notify(title, message, icon=None, timeout=2):
    notification.notify(
        title=title,
        app_name="CyanSystemManager",
        message=message,
        app_icon=os.path.join(ICONS_FOLDER_PATH, icon) if icon else None,
        timeout=timeout
    )


class Application:
    window_props_values = {
        "monitor_id": "",
        "x": 0,
        "y": 0,
        "width": 0,
        "height": 0,
        "win_state": "normal",
        "order": False
    }

    def __init__(self, name, window_kw, excluded_kw, proc_name, path, window_props={}, process=None, arguments="", runas=False, startup=False):
        self.loaded_name = name
        self.name = name
        self.process = process
        self.window_kw = window_kw
        self.excluded_kw = excluded_kw
        self.window_props = {k: window_props.get(k, v) for k, v in self.window_props_values.items()}
        self.proc_name = proc_name
        self.path = path.replace("TOOLS", TOOLS_PATH).replace("\\", "/")
        self.arguments = arguments
        self.runas = runas
        self.startup = startup
    
    def equals(self, application):
        if not application:
            return False
        return json.dumps(self.to_dict()) == json.dumps(application.to_dict())

    def to_dict(self):
        return {
            "window_kw": self.window_kw,
            "excluded_kw": self.excluded_kw,
            "window_props": {k: self.window_props[k] for k in self.window_props_values},
            "proc_name": self.proc_name,
            "path": self.path,
            "arguments": self.arguments,
            "runas": self.runas,
            "startup": self.startup
        }

    def __repr__(self):
        return f"Application(name={self.name}, state={'ACTIVE' if self.process else 'DOWN'})"


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


def find_process_by_exe(exe_path: str, kill: bool=False, relaunch: bool=False, args: tuple=()):
    procs = []
    process_name = os.path.basename(exe_path).lower()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'].lower() == process_name:
                if not kill:
                    procs.append(proc)
                else:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if relaunch and not procs:
        print(f"Launching {exe_path}")
        subprocess.Popen([exe_path] + list(args))
    return procs
