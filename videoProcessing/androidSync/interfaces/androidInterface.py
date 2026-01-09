import sys
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import *


class AndroidInterface(Interface):
    adb_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform-tools", "adb.exe")
    root = "/sdcard"
    local_root = ""
    android_serial = ""
    folder_map = {}

    def __init__(self, local_id, interface_id, signal, args):
        super().__init__(local_id, interface_id, signal)
        for k, v in args.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def device_connected(self):
        try:
            self.parse_device_info()
            return True
        except Exception as e:
            return False

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
        # Get directories
        cmd = [self.adb_path, '-s', self.android_serial, 'shell', 'find', remote_path.get_unix_path(), '-type', 'd']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        directories = []

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            for line in result.stdout.splitlines():
                if signal["kill"]:
                    return
                directories.append(CPath(line.strip()).origin)
        
        # Get all files
        cmd = [self.adb_path, '-s', self.android_serial, 'shell', 'ls', '-laR', remote_path.get_unix_path()]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        files_to_add = []

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            directory = ""
            for line in result.stdout.splitlines():
                if signal["kill"]:
                    return
                parts = line.split()
                if len(parts) < 6:
                    if len(parts) > 0 and parts[0][0] == "/":
                        directory = " ".join(parts).replace(":", "")
                    continue
                _, _, _, _, size, date, time, *filename = parts
                filename = " ".join(filename)
                folder_path = CPath(directory).relative_to(CPath(remote_root))
                full_filename = folder_path.append(filename)
                files[full_filename.origin] = files.get(full_filename.origin, {"local": None, "remote": None})
                local_path = full_filename.prepend(signal['interface'].local_root)
                remote_path = full_filename.prepend(signal['interface'].root)
                if remote_path.origin not in directories:
                    date = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                    files_to_add.append((full_filename, local_path, remote_path, date, False, int(size)))
        return files_to_add
    
    def get_remote_sync_md(self, remote_path):
        md_path = f"{remote_path.get_unix_path()}/{SYNC_MD_FILE}"
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_file = tmp.name
        cmd = [self.adb_path, "-s", self.android_serial, "pull", md_path, tmp_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            Path(tmp_file).unlink(missing_ok=True)
            return {}
        try:
            with open(tmp_file, "r", encoding="utf-8") as f:
                self.full_remote_md = json.load(f)
                return self.full_remote_md.get(self.share_id(), {})
        except json.JSONDecodeError:
            return {}
        finally:
            Path(tmp_file).unlink()
    
    def set_remote_sync_md(self, data, remote_path):
        md_path = os.path.join(remote_path.get_unix_path(), SYNC_MD_FILE)
        merged_data = {**self.full_remote_md, self.share_id(): data}
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8", suffix=".json") as tmp:
            json.dump(merged_data, tmp, indent=2)
            tmp_file = tmp.name
        cmd = [self.adb_path, "-s", self.android_serial, "push", tmp_file, md_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        Path(tmp_file).unlink()
        if result.returncode != 0:
            raise Exception(f"ADB push failed: {result.stderr}")

    def delete_file_from_remote(self, remote_path):
        cmd = [self.adb_path, '-s', self.android_serial, 'shell', f'test -e "{remote_path.get_unix_path()}" && rm -f "{remote_path.get_unix_path()}"']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise Exception(f"Error removing remote file: {result.stderr}")

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