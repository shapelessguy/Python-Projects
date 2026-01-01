import os
from datetime import datetime
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".config")


def scale_bytes(bytes, decimal=1):
    if bytes > 1024**3:
        return f"{round(bytes / (1024**3), decimal)}GB"
    elif bytes > 1024**2:
        return f"{round(bytes / (1024**2), decimal)}MB"
    elif bytes > 1024:
        return f"{round(bytes / 1024, decimal)}KB"
    else:
        return f"{round(bytes, 0)}B"


class Interface:
    unix = True
    root = ''
    local_root = ''
    folder_map = {}

    def parse_device_info(self):
        raise Exception("Unhandled function!")
    
    def get_memory_consumption(self):
        raise Exception("Unhandled function!")

    def get_remote_files(self, signal, remote_path, files, remote_root):
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
            date = date.replace(second=0, microsecond=0)

            if master_local and master_local.origin != "":
                file_id = CPath(full_path).relative_to(master_local)
                full_filename = file_id.prepend(relative_path.origin)
                local_path = file_id.prepend(master_local.origin)
                remote_path = full_filename.prepend(signal['interface'].root)
            else:
                full_filename = CPath(full_path).relative_to(CPath(signal['interface'].local_root if not remote else signal['interface'].root))
                local_path = full_filename.prepend(signal['interface'].local_root)
                remote_path = full_filename.prepend(signal['interface'].root)
            files_to_add.append((full_filename, local_path, remote_path, date, int(size)))
    return files_to_add


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
