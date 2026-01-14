import os
import traceback
from plyer import notification
from registered_functions import register_functions_and_hotkeys, Signal
from start_and_shutdown import register_start_and_shutdown_tasks
from utils import wait, ICONS_FOLDER_PATH, pprint


def initialize(signal: Signal):
    notification.notify(
        title="CyanSystemManager",
        app_name="CyanSystemManager",
        message=f"Running",
        app_icon=os.path.join(ICONS_FOLDER_PATH, "cyan_system_manager.ico"),
        timeout=2
    )
    register_functions_and_hotkeys(signal)
    register_start_and_shutdown_tasks(signal)

try:
    signal = Signal()
    initialize(signal)

    signal.start_threads()
    while signal.is_alive():
        wait(signal, 1000)
except Exception:
    pprint(traceback.format_exc())
except KeyboardInterrupt:
    pass

signal.kill()
pprint("App killed")
