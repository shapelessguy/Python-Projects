import sys
import os
import platform
import shutil
import json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import *


class HHDInterface(Interface):
    root = ""
    local_root = ""
    folder_map = {}

    def __init__(self, local_id, interface_id, signal, args):
        super().__init__(local_id, interface_id, signal)
        for k, v in args.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def device_connected(self):
        return os.path.exists(self.root)

    def parse_device_info(self):
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

    def get_remote_sync_md(self, remote_path):
        md_path = os.path.join(remote_path.get_unix_path(), SYNC_MD_FILE)
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        result = {}
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as file:
                self.full_remote_md = json.load(file)
                result = self.full_remote_md.get(self.share_id(), {})
        return result

    def delete_file_from_remote(self, remote_path):
        target_path = remote_path.get_unix_path()
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
        except OSError as e:
            raise Exception(f"Error: {e}")

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