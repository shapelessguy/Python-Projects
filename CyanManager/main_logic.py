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
from utils import pprint, notify, Application, ENV_PATH, CONFIGURATIONS_PATH


class Signal:
    kill_flag = False
    restart_flag = False
    _preferences: dict
    reg_functions: RegisteredFunctions
    threads: dict[str, threading.Thread]
    last_interaction: datetime
    ui_manager = None

    def __init__(self):
        self.load_preferences()
        self.threads = {}
        self.kill_flag = False
    
    def load_preferences(self):
        env_vars = dotenv_values(ENV_PATH)
        if "PROFILE" not in env_vars:
            with open(ENV_PATH, "a", encoding="utf8") as file:
                file.write("PROFILE=default\n")
            env_vars = dotenv_values(ENV_PATH)
        self.profile = env_vars["PROFILE"]
        config = [x for x in os.listdir(CONFIGURATIONS_PATH) if x.replace(".json", "") == self.profile]
        if not len(config):
            raise Exception(f"PROFILE {self.profile} not found!")
        profile_path = os.path.join(CONFIGURATIONS_PATH, config[0])
        if os.path.exists(profile_path):
            with open(profile_path, "r") as file:
                self._preferences = json.load(file)
        else:
            raise Exception(f"File {profile_path} not found!")
    
    def get_applications(self):
        applications = json.loads(json.dumps(self._preferences["applications"]))
        return [Application(a_name, **a) for a_name, a in applications.items()]
    
    def get_restart_options(self):
        restart_opt = json.loads(json.dumps(self._preferences["restart"]))
        return restart_opt
    
    def get_roomserver_settings(self):
        rs_settings = json.loads(json.dumps(self._preferences["roomserver_settings"]))
        return rs_settings
    
    def get_audio_devices(self):
        devices = json.loads(json.dumps(self._preferences["audio_devices"]))
        return devices
    
    def save_preferences(self):
        profile_path = os.path.join(CONFIGURATIONS_PATH, self.profile + ".json")
        with open(profile_path, "w") as file:
            json.dump(self._preferences, file, indent=4)
    
    def set_reg_functions(self, reg_functions):
        self.reg_functions = reg_functions
    
    def register_thread(self, name, target, args: tuple):
        self.threads[name] = threading.Thread(target=target, args=args)
    
    def start_threads(self):
        for name, t in self.threads.items():
            if not t.is_alive():
                pprint(f"Starting thread: {name}")
                t.start()
    
    def join_threads(self):
        for t in self.threads.values():
            if t.is_alive():
                t.join()
    
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
            pprint("startLoop")
            signal = Signal()
            pprint("definedSignal")
            
            signal.ui_manager = UI(signal)

            register_functions_and_hotkeys(signal)
            register_start_and_shutdown_tasks(signal)
            signal.start_threads()

            form_closed = signal.ui_manager.execute("wait_for_close")
            pprint("endLoop")
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
