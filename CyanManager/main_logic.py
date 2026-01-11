import time
import os
import traceback
from plyer import notification
from registered_functions import register_functions_and_hotkeys, Signal
from settings import *


def initialize(signal: Signal):
    notification.notify(
        title="CyanSystemManager",
        app_name="CyanSystemManager",
        message=f"Running",
        app_icon=os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.ico"),
        timeout=2
    )
    signal.set_applications(all_apps)
    register_functions_and_hotkeys(signal)


def monitor(signal: Signal):
    while signal.is_alive():
        time.sleep(1)

try:
    signal = Signal()
    initialize(signal)
    monitor(signal)
except Exception:
    print(traceback.format_exc())
except KeyboardInterrupt:
    pass

signal.kill()
print("App killed")
