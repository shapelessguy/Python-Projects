import os
import json
import time
import threading
import datetime
import traceback
import sys
import ctypes
from gui.manage_ui import UI
from dotenv import dotenv_values
from registered_functions import register_functions_and_hotkeys, RegisteredFunctions
from start_and_shutdown import register_start_and_shutdown_tasks
from utils import pprint, notify, Application, ENV_PATH, CONFIGURATIONS_PATH, EXE_MAP_PATH


class ThreadManager():
    def __init__(self, signal, name, target, args):
        self.signal = signal
        self.name = name
        self.target = target
        self.args = args
        self.to_kill = False
        self.thread = None
    
    def is_alive(self):
        return self.thread and self.thread.is_alive()
    
    def start(self):
        pprint(f"Starting thread: {self.name}")
        self.thread = threading.Thread(target=self.target, args=(self, *self.args))
        self.thread.start()

    def kill(self):
        pprint(f"Killing thread: {self.name}")
        self.to_kill = True

    def join(self):
        if self.thread:
            self.thread.join()


class Signal:
    kill_flag = False
    restart_flag = False
    _preferences: dict
    reg_functions: RegisteredFunctions
    threads: dict[str, ThreadManager]
    last_interaction: datetime
    ui_manager = None
    profile: str

    def __init__(self):
        self.load_exe_table()
        self.load_preferences()
        self.threads = {}
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
        with open(ENV_PATH, "r", encoding="utf8") as file:
            lines = file.readlines()
        new_lines = []
        for l in lines:
            if l.startswith("PROFILE="):
                new_lines.append(f"PROFILE={self.profile}\n")
            else:
                new_lines.append(l)
        with open(ENV_PATH, "w", encoding="utf8") as file:
            file.writelines(new_lines)
        self.load_preferences()
        self.restart_threads()
    
    def load_preferences(self):
        env_vars = dotenv_values(ENV_PATH)
        if "PROFILE" not in env_vars:
            with open(ENV_PATH, "a", encoding="utf8") as file:
                file.write("PROFILE=default\n")
            env_vars = dotenv_values(ENV_PATH)
        self.profile = env_vars["PROFILE"]
        if self.profile not in self.get_all_profiles():
            raise Exception(f"PROFILE {self.profile} not found!")
        profile_path = os.path.join(CONFIGURATIONS_PATH, self.profile + ".json")
        if os.path.exists(profile_path):
            with open(profile_path, "r") as file:
                self._preferences = json.load(file)
        else:
            raise Exception(f"File {profile_path} not found!")
    
    def get_current_profile(self):
        applications = json.loads(json.dumps(self._preferences["applications"]))
        return [Application(a_name, **a) for a_name, a in applications.items()]
    
    def get_applications(self):
        applications = json.loads(json.dumps(self._preferences["applications"]))
        return [Application(a_name, **a) for a_name, a in applications.items()]

    def set_applications(self, applications):
        self._preferences["applications"] = {a.name: a.to_dict() for a in sorted(applications, key=lambda x: x.name)}
        self.save_preferences()
    
    def get_restart_options(self):
        restart_opt = json.loads(json.dumps(self._preferences["restart"]))
        return restart_opt
    
    def set_restart_options(self, ro):
        self._preferences["restart"] = ro
        self.save_preferences()
    
    def get_roomserver_settings(self):
        rs_settings = json.loads(json.dumps(self._preferences["roomserver_settings"]))
        return rs_settings
    
    def set_roomserver_settings(self, rs):
        self._preferences["roomserver_settings"] = rs
        self.save_preferences()
    
    def get_audio_devices(self):
        devices = json.loads(json.dumps(self._preferences["audio_devices"]))
        return devices
    
    def set_audio_devices(self, ad):
        self._preferences["audio_devices"] = ad
        self.save_preferences()
    
    def save_preferences(self):
        profile_path = os.path.join(CONFIGURATIONS_PATH, self.profile + ".json")
        with open(profile_path, "w") as file:
            json.dump(self._preferences, file, indent=4)
    
    def set_reg_functions(self, reg_functions):
        self.reg_functions = reg_functions
    
    def register_thread(self, name, target, args: tuple=()):
        self.threads[name] = ThreadManager(self, name, target, args)
    
    def start_threads(self):
        for tm in self.threads.values():
            if not tm.is_alive():
                tm.start()
    
    def kill_threads(self):
        for tm in self.threads.values():
            if not tm.is_alive():
                tm.kill()
    
    def join_threads(self):
        for tm in self.threads.values():
            if tm.is_alive():
                tm.join()
    
    def restart_threads(self):
        for tm in self.threads.values():
            if tm.is_alive():
                tm.kill()
        for tm in self.threads.values():
            tm.join()
        for tm in self.threads.values():
            tm.start()
    
    def kill(self):
        self.kill_flag = True
    
    def restart(self):
        self.kill_flag = True
        self.restart_flag = True
    
    def is_alive(self):
        return not self.kill_flag


def main():
    restart = True
    sys.argv.append('--no-sandbox')
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CyanManager")
    notify(title="CyanManager", message=f"Running", icon="cyan_system_manager.ico")
    
    while restart:
        form_closed = 1
        restart = False
        signal = None
        try:
            signal = Signal()
            
            register_functions_and_hotkeys(signal)
            register_start_and_shutdown_tasks(signal)
            signal.ui_manager = UI(signal)

            signal.start_threads()
            signal.ui_manager.start_gui_tasks()

            form_closed = signal.ui_manager.execute("wait_for_close")
        except Exception:
            pprint(traceback.format_exc())
        except KeyboardInterrupt:
            pass
        if signal:
            signal.kill()
            signal.join_threads()
        restart = signal.ui_manager.restart

        if restart:    
            pprint("CyanManager restarted")
            time.sleep(2)

    pprint("CyanManager terminated")
    if form_closed == 1:
        sys.exit()
    else:
        sys.exit(form_closed)


if __name__ == "__main__":
    main()
