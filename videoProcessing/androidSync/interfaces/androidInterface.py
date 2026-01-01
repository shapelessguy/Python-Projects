import sys
import os
import subprocess
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import *


class AndroidInterface(Interface):
    adb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform-tools", "adb.exe")
    root = "/sdcard"
    local_root = r"C:\Users\Claudio\Videos\Xiaomi"
    android_serial = "eykfq8vwcq9ham9d"
    folder_map = {
        "Documents": {"master_local": r"C:\Users\Claudio\Documents\Documenti"},
        "Download": {"prune": True},
        "DCIM": {},
        "Pictures": {},
        "Movies": {},
        "Music": {},
        "Audiobooks": {},
    }

    def parse_device_info(self):
        cmd = [self.adb_path, '-s', self.android_serial, "shell", "getprop ro.product.brand; getprop ro.product.model"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(result.stderr)
        return "Model: " + result.stdout.strip().replace("\n", " - ")
    
    def get_memory_consumption(self):
        cmd = [self.adb_path, '-s', self.android_serial, "shell", "df", CPath(self.root).get_unix_path()]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(result.stderr)

        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            raise Exception("Unexpected df output")

        parts = lines[1].split()
        _, total_kb, used_kb, _, percent, _ = parts

        total = int(total_kb) * 1024
        used = int(used_kb) * 1024
        return used, total, percent

    def get_remote_files(self, signal, remote_path, files, remote_root):
        cmd = [self.adb_path, '-s', self.android_serial, 'shell', 'ls', '-lR', remote_path.get_unix_path()]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        files_to_add = []

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            folder = ""
            for line in result.stdout.splitlines():
                if signal["kill"]:
                    return
                parts = line.split()
                if len(parts) < 6:
                    if len(parts) > 0 and parts[0][0] == "/":
                        folder = " ".join(parts).replace(":", "")
                    continue
                _, _, _, _, size, date, time, *filename = parts
                filename = " ".join(filename)
                if "." in filename:
                    folder_path = CPath(folder).relative_to(CPath(remote_root))
                    full_filename = folder_path.append(filename)
                    files[full_filename.origin] = files.get(full_filename.origin, {"local": None, "remote": None})
                    local_path = full_filename.prepend(signal['interface'].local_root)
                    remote_path = full_filename.prepend(signal['interface'].root)
                    date = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                    files_to_add.append((full_filename, local_path, remote_path, date, int(size)))
        return files_to_add

    def copy_file_to_local(self, local_path, remote_path):
        cmd = [self.adb_path, '-s', self.android_serial, 'pull', '-a', remote_path.get_unix_path(), local_path.get_unix_path()]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")

    def copy_file_to_remote(self, local_path, remote_path):
        cmd = [self.adb_path, '-s', self.android_serial, 'push', '-a', local_path.get_unix_path(), remote_path.get_unix_path()]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")

    def move_file_from_remote_to_remote(self, remote_path, dest_path):
        dest_dir = os.path.dirname(dest_path.get_unix_path())
        cmd = [self.adb_path, '-s', self.android_serial, 'shell', f'mkdir -p "{dest_dir}" && mv "{remote_path.get_unix_path()}" "{dest_path.get_unix_path()}"']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")