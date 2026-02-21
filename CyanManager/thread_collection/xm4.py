from utils import XM4_EXE_PATH, manage_exe_execution


NAME = "XM4-1000"
PARAMETERS = {}


def entrypoint(thread_manager):
    manage_exe_execution(thread_manager, XM4_EXE_PATH)
