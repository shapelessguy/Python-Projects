from utils import RVX_EXE_PATH, manage_exe_execution


NAME = "3RVX - Volume"
PARAMETERS = {}


def entrypoint(thread_manager):
    manage_exe_execution(thread_manager, RVX_EXE_PATH)
