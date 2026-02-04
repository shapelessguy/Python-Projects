import os
import hashlib
import json
import re
import unicodedata


def query_to_hash(query: str, algo="sha1", length=12):
    h = hashlib.new(algo)
    h.update(query.encode("utf-8"))
    return h.hexdigest()[:length]


AI_TASKS_PATH = os.path.join(os.path.dirname(__file__), "ai_tasks")
AI_TASKS = [x.replace(".py", "") for x in os.listdir(AI_TASKS_PATH) if x.endswith(".py")]
WORKSPACES_PATH = os.path.join(os.path.dirname(__file__), "workspaces")
if not os.path.exists(WORKSPACES_PATH):
    os.mkdir(WORKSPACES_PATH)


PAPER_LOCATION_MAP_PATH = os.path.join(WORKSPACES_PATH, "paper_loc.json")
FAILED_PDF_RETRIEVAL_PATH = os.path.join(WORKSPACES_PATH, "failed_pdfs.json")
SAVED_RESPONSES_PATH = os.path.join(WORKSPACES_PATH, "saved_responses.json")
CUSTOM_TEXT_PATH_TEMPLATE = os.path.join(WORKSPACES_PATH, "WORKSPACE_NAME", "custom_text.py")


# PDFS_PATH = os.path.join(WORKSPACES_PATH, "pdfs")
# EXTRACTED_PATH = os.path.join(WORKSPACES_PATH, "extracted_text")
# if not os.path.exists(PDFS_PATH):
#     os.mkdir(PDFS_PATH)
# if not os.path.exists(EXTRACTED_PATH):
#     os.mkdir(EXTRACTED_PATH)


def create_folder(workspace_name: str, folder_name: str, create: bool):
    path = os.path.join(WORKSPACES_PATH, workspace_name, folder_name)
    if not os.path.exists(path):
        if not create:
            raise Exception(f"Folder {path} not found!")
        os.makedirs(path, exist_ok=True)
    return path


def get_hash_map(workspace_name: str):
    path = os.path.join(get_raw_paper_headers(workspace_name), "hashes.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            json.dump({}, file)
    return path


def get_raw_paper_headers(workspace_name: str, create=True):
    return create_folder(workspace_name, "raw_paper_headers", create)


def get_queries_path(workspace_name: str, create=True):
    path = os.path.join(WORKSPACES_PATH, workspace_name, "batches/queries")
    if not os.path.exists(path):
        raise Exception("NONO", f"|{workspace_name}|")
    return create_folder(workspace_name, "batches/queries", create)


def get_responses_path(workspace_name: str, create=True):
    path = os.path.join(WORKSPACES_PATH, workspace_name, "batches/responses")
    if not os.path.exists(path):
        raise Exception("NONO", f"|{workspace_name}|")
    return create_folder(workspace_name, "batches/responses", create)


def get_pdfs_path(workspace_name: str, create=True):
    return create_folder(workspace_name, "pdfs", create)


def get_user_pdfs_path(workspace_name: str, create=True):
    return create_folder(workspace_name, "user_pdfs", create)


def get_extracted_path(workspace_name: str, create=True):
    return create_folder(workspace_name, "extracted_text", create)


def get_saved_pdfs_path(workspace_name: str, create=True):
    return create_folder(workspace_name, "saved_pdfs", create)


def clean_pdf_name(title: str, max_length: int = 150) -> str:
    if not title:
        raise Exception("No title provided")
    name = unicodedata.normalize("NFKD", title)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'[^\w\s.-]', '_', name)
    name = re.sub(r'[\s_]+', '_', name)
    name = name.strip('._')
    if max_length and len(name) > max_length:
        name = name[:max_length].rstrip('._')
    return name


def get_user_pdf_map(workspace_name: str):
    path = os.path.join(get_user_pdfs_path(workspace_name), "user_pdf_map.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as file:
            json.dump({}, file)
    return path


SYMBOLS = {
    " ": "_",
    "*": "SYstar",
    "+": "SYminus",
    "-": "SYplus",
    "(": "SYopen",
    ")": "SYclose",
    '"': "SYquote",
    "|": "SYpipe",
    "\n": "",
    "\\n": "",
}


def decode_name(hash: str, workspace: str):
    with open(get_hash_map(workspace), "r") as file:
        hashes = json.load(file)
        return hashes[hash.replace("query_", "").replace(".json", "")]
    raise Exception


def encode_name(name: str, workspace: str):
    hash = query_to_hash(name)
    with open(get_hash_map(workspace), "r") as file:
        hashes = json.load(file)
        hashes[hash] = name
    with open(get_hash_map(workspace), "w") as file:
        json.dump(hashes, file)
    return f"query_{hash}.json"


# import os
# import psutil
import time
# import subprocess
# import json
# from plyer import notification
from datetime import datetime


# APP_DATA_PATH = os.path.dirname(os.environ.get("APPDATA", "C:/Users/Default/AppData/Roaming"))
# C_DRIVE_PATH = os.path.splitdrive(os.environ.get("ProgramFiles", "C:/Program Files"))[0]
# PROGRAM_FILES_X86_PATH = os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")
# PROGRAM_FILES_PATH = os.environ.get("ProgramFiles", "C:/Program Files")

# TOOLS_PATH = os.path.join(os.path.dirname(__file__), 'tools')
# CYANSYNC_LOGS_PATH = os.path.join(TOOLS_PATH, 'cyanSync', 'logs')
# SV_EXE_PATH = os.path.join(TOOLS_PATH, 'svcl.exe')
# MULTIMONITOR_FOLDER_PATH = os.path.join(TOOLS_PATH, "MultiMonitorTool")
# RVX_EXE_PATH = os.path.join(TOOLS_PATH, "3RVX_portable", "3RVX.exe")
# XM4_EXE_PATH = os.path.join(TOOLS_PATH, "Xm4Battery-5.11.14", "Xm4Battery", "bin", "Release", "net10.0-windows", "Xm4Battery.exe")
# KEYBOARD_HOTKEYS_EXE = os.path.join(TOOLS_PATH, "KeyboardHotkeys", "KeyboardHotkeys", "bin", "Release", "net10.0-windows", "KeyboardHotkeys.exe")
# TIMER_EXE = os.path.join(TOOLS_PATH, "Timer", "Timer", "bin", "Release", "net10.0-windows", "Timer.exe")
# MULTIMONITOR_EXE_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "MultiMonitorTool.exe")
# TEMP_MONITOR_CONF_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "temp_config.cfg")
# MONITOR_CONF_PATH = os.path.join(MULTIMONITOR_FOLDER_PATH, "config.cfg")

# DOCUMENTS_PATH = os.path.join(os.path.expanduser("~"), "Documents")
# CODEBASE_PATH = os.path.join(DOCUMENTS_PATH, "codebase")
ICONS_FOLDER_PATH = os.path.join(os.path.dirname(__file__), 'gui', 'icons')
# CONFIGURATIONS_PATH = os.path.join(os.path.dirname(__file__), 'configurations')
# EXE_MAP_PATH = os.path.join(os.path.dirname(__file__), 'exe_map.json')
# ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
# ERR_FLAG = "CyanManagerError"


class Tee:
    def __init__(self, log_queue, stream):
        self.log_queue = log_queue
        self.stream = stream

    def write(self, msg):
        self.stream.write(msg)
        self.stream.flush()
        self.log_queue.put(msg)

    def flush(self):
        self.stream.flush()


ICONS_FOLDER_PATH = os.path.join(os.path.dirname(__file__), 'gui', 'icons')
def wait(signal, ms: int):
    while signal.is_alive():
        remaining = ms
        while remaining > 0 and signal.is_alive():
            time.sleep(min(remaining / 1000, 0.05))
            remaining -= 50
        break


def pprint(*args, dt_format="%Y-%m-%d %H:%M:%S", **kwargs):
    """
    Prints messages with a timestamp.
    All args are joined into a single string to avoid splitting.
    """
    timestamp = datetime.now().strftime(dt_format)
    # Join all args with spaces into one string
    message = " ".join(str(arg) for arg in args)
    print(f"[{timestamp}] {message}", **kwargs, flush=True)
