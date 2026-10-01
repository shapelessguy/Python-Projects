import os
from utils import manage_exe_execution


NAME = "3RVX - Volume"
PARAMETERS = {}

RVX_EXE_PATH = os.path.join(os.path.dirname(__file__), "tools", "3RVX_portable", "3RVX.exe")


def entrypoint(thread_manager):
    manage_exe_execution(thread_manager, RVX_EXE_PATH)
