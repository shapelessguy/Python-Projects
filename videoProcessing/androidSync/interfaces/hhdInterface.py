import sys
import os
import platform
import shutil
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import *


class HHDInterface(Interface):
    root = r"C:\Users\Claudio\Videos\folder_remote"
    local_root = r"C:\Users\Claudio\Videos\folder_local"
    folder_map = {
        "Sync": {"master_local": r"C:\Users\Claudio\Videos\folder_local\Sync"}
    }

    def parse_device_info(self):
        system = platform.system()
        release = platform.release()
        machine = platform.machine()
        processor = platform.processor()

        return (
            f"Machine: {machine} - "
            f"Processor: {processor}"
        )
    
    def get_memory_consumption(self):
        usage = shutil.disk_usage(self.root)

        total = usage.total
        used = usage.used
        percent = f"{int((used / total) * 100)}%"

        return used, total, percent

    def get_remote_files(self, signal, remote_path, files, remote_root):
        return get_local_files(signal, remote_path, remote=True)

    def copy_file_to_local(self, local_path, remote_path):
        src = remote_path.get_unix_path()
        dst = local_path.get_unix_path()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            raise Exception(f"Error: {e}")

    def copy_file_to_remote(self, local_path, remote_path):
        src = local_path.get_unix_path()
        dst = remote_path.get_unix_path()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            raise Exception(f"Error: {e}")

    def move_file_from_remote_to_remote(self, remote_path, dest_path):
        src = remote_path.get_unix_path()
        dst = dest_path.get_unix_path()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.move(src, dst)
        except OSError as e:
            raise Exception(f"Error: {e}")