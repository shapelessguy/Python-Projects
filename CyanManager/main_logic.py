import os
import json
import threading
import datetime
import traceback
import sys
import ctypes
import pkgutil

# PyQt5 bundles an old Microsoft C++ runtime (msvcp140 14.26). Whichever copy
# loads first serves the whole process, and torch (the STT service) fails on
# the old one with WinError 1114: load Windows' own before PyQt5 does.
for _dll in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
    try:
        ctypes.WinDLL(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", _dll))
    except OSError:
        pass

import services
import api_auth
import service_deps
from gui.manage_ui import UI
from registered_functions import register_functions, RegisteredFunctions
from utils import Tee, notify, Application, Thread, ENV_PATH, CONFIGURATIONS_PATH, EXE_MAP_PATH, PROFILE_PATH


class ThreadManager():
    def __init__(self, signal, name, target, parameters, args, module=None):
        self.signal = signal
        self.name = name
        self.module = module  # its folder in services/
        self.target = target  # None: its requirements are not installed (service_deps.py)
        self.parameters = parameters
        self.args = args
        self.to_kill = False
        self.thread = None
    
    def is_alive(self):
        return self.thread and self.thread.is_alive()
    
    def get_params(self):
        saved_parameters = {}
        for t in self.signal.get_threads():
            if t.name == self.name:
                saved_parameters = t.parameters
        parameters = {**{k: v.default for k, v in self.parameters.items()}, **saved_parameters}
        return parameters
    
    def get_param(self, name):
        available_params = self.get_params().keys()
        if name not in available_params:
            print(f"Requested param {name} but not available: {available_params}")
        return self.get_params().get(name, None)
    
    def installed(self):
        return self.target is not None

    def start(self):
        if not self.installed():
            return
        print(f"Starting thread: {self.name}")
        self.to_kill = False
        self.thread = threading.Thread(target=self.target, args=(self, *self.args))
        self.thread.start()

    def kill(self):
        print(f"Killing thread: {self.name}")
        self.to_kill = True

    def join(self):
        if self.thread:
            self.thread.join()


class Signal:
    kill_flag = False
    restart_flag = False
    _preferences: dict
    reg_functions: RegisteredFunctions
    thread_managers: dict[str, ThreadManager]
    last_interaction: datetime
    info: dict
    ui_manager = None
    profile: str

    def __init__(self):
        
        from queue import Queue
        self.log_queue = Queue()

        self.info = {}
        self.info["audio_device"] = ""
        self.info["volume"] = 0

        # The launcher redirects to a log file, cp1252 by default: a window
        # title with other characters would make Tee drop the whole line.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout = Tee(self.log_queue, sys.stdout)
        sys.stderr = Tee(self.log_queue, sys.stderr)
        self.load_exe_table()
        self.load_preferences()
        self.thread_managers = {}
        self.session_locked = False
        self.kill_flag = False
    
    def get_all_profiles(self):
        return [x.replace(".json", "") for x in os.listdir(CONFIGURATIONS_PATH)]

    def load_exe_table(self):
        self.exe_map = {}
        if not os.path.exists(EXE_MAP_PATH):
            with open(EXE_MAP_PATH, "w", encoding="utf8") as file:
                json.dump(self.exe_map, file)
        else:
            with open(EXE_MAP_PATH, "r", encoding="utf8") as file:
                self.exe_map = json.load(file)
    
    def update_exe_table(self, exe_map: dict):
        for k, v in exe_map.items():
            self.exe_map[k] = v
        with open(EXE_MAP_PATH, "w", encoding="utf8") as file:
            json.dump(self.exe_map, file, indent=2)
    
    def set_profile(self, profile_name):
        if profile_name in self.get_all_profiles():
            self.profile = profile_name
        with open(PROFILE_PATH, "w", encoding="utf8") as file:
            file.write(self.profile + "\n")
        self.load_preferences()
        self.restart_thread_managers()

    def read_profile(self):
        """The profile chosen on this PC (profile.txt), "default" the first time.
        It used to be PROFILE= in .env: moved from there once."""
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf8") as file:
                return file.read().strip() or "default"
        profile = "default"
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf8") as file:
                lines = file.readlines()
            kept = [l for l in lines if not l.startswith("PROFILE=")]
            for l in lines:
                if l.startswith("PROFILE="):
                    profile = l.split("=", 1)[1].strip() or profile
            if len(kept) != len(lines):
                with open(ENV_PATH, "w", encoding="utf8") as file:
                    file.writelines(kept)
        with open(PROFILE_PATH, "w", encoding="utf8") as file:
            file.write(profile + "\n")
        return profile

    def load_preferences(self):
        self.profile = self.read_profile()
        if self.profile not in self.get_all_profiles():
            raise Exception(f"PROFILE {self.profile} not found!")
        profile_path = os.path.join(CONFIGURATIONS_PATH, self.profile + ".json")
        if os.path.exists(profile_path):
            with open(profile_path, "r") as file:
                self._preferences = json.load(file)
        else:
            raise Exception(f"File {profile_path} not found!")
    
    def get_applications(self):
        applications = json.loads(json.dumps(self._preferences["applications"]))
        return [Application(a_name, **a) for a_name, a in applications.items()]

    def set_applications(self, applications: list[Application]):
        self._preferences["applications"] = {a.name: a.to_dict() for a in sorted(applications, key=lambda x: x.name)}
        self.save_preferences()
    
    def get_threads(self):
        threads = json.loads(json.dumps(self._preferences["threads"]))
        return [Thread(t_name, **t) for t_name, t in threads.items()]

    def set_threads(self, threads: list[Thread]):
        self._preferences["threads"] = {t.name: t.to_dict() for t in sorted(threads, key=lambda x: x.name)}
        self.save_preferences()
    
    def save_preferences(self):
        profile_path = os.path.join(CONFIGURATIONS_PATH, self.profile + ".json")
        with open(profile_path, "w") as file:
            json.dump(self._preferences, file, indent=4)
    
    def set_reg_functions(self, reg_functions):
        self.reg_functions = reg_functions
    
    def register_thread(self, name, target, parameters, args: tuple=(), module=None):
        self.thread_managers[name] = ThreadManager(self, name, target, parameters, args, module)
    
    def start_thread_managers(self):
        threads = {t.name: t for t in self.get_threads()}
        for tm in self.thread_managers.values():
            enabled = True if tm.name not in threads else threads[tm.name].enabled
            if not tm.is_alive() and enabled:
                tm.start()
    
    def kill_thread_managers(self):
        for tm in self.thread_managers.values():
            if tm.is_alive():
                tm.kill()
    
    def join_thread_managers(self):
        for tm in self.thread_managers.values():
            if tm.is_alive():
                tm.join()
    
    def restart_thread_managers(self):
        self.kill_thread_managers()
        self.join_thread_managers()
        self.start_thread_managers()
    
    def kill(self):
        self.kill_flag = True
    
    def restart(self):
        self.kill_flag = True
        self.restart_flag = True
    
    def is_alive(self):
        return not self.kill_flag


def register_threads(signal):
    # Each service is services/<name>/service.py, next to its own
    # requirements.txt and tools/ (see services/__init__.py).
    for _, module_name, is_pkg in pkgutil.iter_modules(services.__path__):
        if module_name.startswith('_') or not is_pkg:
            continue

        try:
            service_deps.load(signal, module_name)
        except Exception as exc:
            print(f"Failed to load/run {module_name}: {exc.__class__.__name__} - {exc}")


def main():
    sys.argv.append('--no-sandbox')
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CyanManager")
    
    form_closed = 1
    signal = None
    try:
        signal = Signal()
        api_auth.load_users()
        register_functions(signal)
        register_threads(signal)
        signal.ui_manager = UI(signal)
        notify(signal, title="CyanManager", message=f"Running", icon="cyan_system_manager.png")

        signal.start_thread_managers()
        signal.ui_manager.start_gui_tasks()

        form_closed = signal.ui_manager.execute("wait_for_close")
    except Exception:
        print(traceback.format_exc())
    except KeyboardInterrupt:
        print("Keyboard interrupt")
        signal.ui_manager.execute("quit_app")

    print("Terminating CyanManager...")
    if signal:
        signal.kill()
        signal.join_thread_managers()

    print("CyanManager terminated")
    if form_closed == 1:
        sys.exit()
    else:
        sys.exit(form_closed)


if __name__ == "__main__":
    main()
