import os
import json
import stat
from datetime import datetime
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".config")
SYNC_MD_FILE = ".syncmd.json"


def scale_bytes(bytes, decimal=1):
    if bytes > 1024**3:
        return f"{round(bytes / (1024**3), decimal)}GB"
    elif bytes > 1024**2:
        return f"{round(bytes / (1024**2), decimal)}MB"
    elif bytes > 1024:
        return f"{round(bytes / 1024, decimal)}KB"
    else:
        return f"{round(bytes, 0)}B"


def print_json(data):
    print(json.dumps(data, indent=2))


class Interface:
    unix = True
    local_id = ''
    interface_id = ''
    root = ''
    local_root = ''
    folder_map = {}
    full_local_md = {}
    full_remote_md = {}

    def share_id(self):
        return f"{self.local_id} -> {self.interface_id}"

    def __init__(self, local_id, interface_id, signal):
        self.local_id = local_id
        self.interface_id = interface_id
        self.signal = signal
        self.connected = True

    def device_connected(self):
        raise Exception("Unhandled function!")

    def parse_device_info(self):
        raise Exception("Unhandled function!")
    
    def get_memory_consumption(self):
        raise Exception("Unhandled function!")

    def get_remote_files(self, signal, remote_path, files, remote_root):
        raise Exception("Unhandled function!")
    
    def get_remote_sync_md(self, remote_path):
        raise Exception("Unhandled function!")

    def delete_file_from_remote(self, remote_path):
        raise Exception("Unhandled function!")

    def copy_file_to_local(self, local_path, remote_path):
        raise Exception("Unhandled function!")

    def copy_file_to_remote(self, local_path, remote_path):
        raise Exception("Unhandled function!")

    def move_file_from_remote_to_remote(self, remote_path, dest_path):
        raise Exception("Unhandled function!")

    
def get_local_files(signal, target_path, relative_path=None, master_local=None, remote=False):
    files_to_add = []
    for root, _, files in os.walk(target_path.get_unix_path()):
        for name in files:
            if signal["kill"]:
                return
            full_path = os.path.join(root, name)
            st = os.stat(full_path)
            size = st.st_size
            date = datetime.fromtimestamp(st.st_mtime)

            if master_local and master_local.origin != "":
                file_id = CPath(full_path).relative_to(master_local)
                full_filename = file_id.prepend(relative_path.origin)
                local_path = file_id.prepend(master_local.origin)
                remote_path = full_filename.prepend(signal['interface'].root)
            else:
                full_filename = CPath(full_path).relative_to(CPath(signal['interface'].local_root if not remote else signal['interface'].root))
                local_path = full_filename.prepend(signal['interface'].local_root)
                remote_path = full_filename.prepend(signal['interface'].root)
            files_to_add.append((full_filename, local_path, remote_path, date, True, int(size)))
    return files_to_add


def remove_local_file(local_path):
    target_path = local_path.get_unix_path()
    try:
        if os.path.exists(target_path):
            os.remove(target_path)
    except OSError as e:
        raise Exception(f"Error: {e}")


def get_local_sync_md(local_path, interface):
    md_path = os.path.join(local_path.get_unix_path(), SYNC_MD_FILE)
    
    result = {}
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as file:
            interface.full_local_md = json.load(file)
            result = interface.full_local_md.get(interface.share_id(), {})
    return result


def set_local_sync_md(data, local_path, interface):
    md_path = os.path.join(local_path.get_unix_path(), SYNC_MD_FILE)
    if os.name == "nt" and os.path.exists(md_path):
        os.chmod(md_path, stat.S_IWRITE)
        os.system(f'attrib -H -S "{md_path}"')
    with open(md_path, "w", encoding="utf-8") as file:
        json.dump({**interface.full_local_md, interface.share_id(): data}, file, indent=2)
    if os.name == "nt":
        os.chmod(md_path, stat.S_IWRITE)
        os.system(f'attrib +H -S "{md_path}"')


class CPath:
    div = "//"
    origin = ""

    def __init__(self, path):
        build = path.replace("/", self.div).replace("\\", self.div)
        while self.div * 2 in build:
            build = build.replace(self.div * 2, self.div)
        self.origin = build
    
    def prepend(self, parent):
        build = parent.replace("/", self.div).replace("\\", self.div) + self.div + self.origin
        while self.div * 2 in build:
            build = build.replace(self.div * 2, self.div)
        return CPath(build)
    
    def append(self, child):
        build = self.origin + self.div + child.replace("/", self.div).replace("\\", self.div)
        while self.div * 2 in build:
            build = build.replace(self.div * 2, self.div)
        return CPath(build)
    
    def relative_to(self, cpath):
        build = self.origin[len(cpath.origin):]
        while self.div * 2 in build:
            build = build.replace(self.div * 2, self.div)
        if build.startswith(self.div):
            build = build[len(self.div):]
        return CPath(build)
    
    def get_unix_path(self):
        return self.origin.replace(self.div, "/")

    def __str__(self):
        return self.origin


class EmptyUI:
    def __init__(self):
        self.ui = None
    
    def execute(self, function_, *args, **kwargs):
        return

    def exit_sync(self, signal):
        signal["kill"] = True
        return

    def setup_ui(self, signal):
        return

    def show_window(self):
        return

    def wait_for_close(self, main_thread):
        main_thread.join()
        return 0

    def quit_app(self):
        return

    def set_text(self, element_name: str, text: str):
        return

    def set_statistics(self, global_stats: dict, size_to_reduce: int=None):
        return

    def set_operation(self, text, color="black"):
        return
