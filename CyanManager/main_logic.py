import traceback
from registered_functions import register_functions_and_hotkeys, Signal
from start_and_shutdown import register_start_and_shutdown_tasks
from utils import wait, pprint, notify


def initialize(signal: Signal):
    notify(title="CyanSystemManager", message=f"Running", icon="cyan_system_manager.ico")
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
