from utils import CYAN_LAUNCHER_PATH, manage_exe_execution


NAME = "Cyan Launcher Manager"
PARAMETERS = {}


def entrypoint(thread_manager):
    manage_exe_execution(thread_manager, CYAN_LAUNCHER_PATH)
