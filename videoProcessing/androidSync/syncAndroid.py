import subprocess
import os
import time
import traceback
from datetime import datetime
from dotenv import dotenv_values
from colorama import init, Fore, Style
init(autoreset=True)


config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".config")
ANDROID_BACKUP_FOLDER = dotenv_values(config_path)["ANDROID_BACKUP_FOLDER"]
ANDROID_SERIAL = dotenv_values(config_path)["ANDROID_SERIAL"]
ADB_PATH = os.path.join(os.path.dirname(__file__), "platform-tools", "adb.exe")
REMOTE_ROOT = "sdcard"


def scale_bytes(bytes):
    if bytes > 1024**3:
        return f"{round(bytes / (1024**3), 1)}GB"
    elif bytes > 1024**2:
        return f"{round(bytes / (1024**2), 1)}MB"
    elif bytes > 1024:
        return f"{round(bytes / 1024, 1)}KB"
    else:
        return f"{round(bytes, 0)}B"


def parse_sdcard_usage():
    cmd = [ADB_PATH, '-s', ANDROID_SERIAL, "shell", "df", "/sdcard"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(result.stderr)

    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        raise Exception("Unexpected df output")

    # second line contains the data
    parts = lines[1].split()
    filesystem, total_kb, used_kb, available_kb, use_percent, mountpoint = parts

    # convert to integers and bytes
    total = int(total_kb) * 1024
    used = int(used_kb) * 1024
    free = int(available_kb) * 1024

    return total, used, free, use_percent


class File:
    def __init__(self, folder, relative_path, remote_path, local_path, last_modified, size):
        self.folder = folder
        self.relative_path = relative_path
        self.remote_path = remote_path
        self.local_path = local_path
        self.last_modified = last_modified
        self.size = size
    
    def get_diff(self, file):
        diff = []
        properties = ["last_modified", "size"]
        for p in properties:
            if getattr(self, p) != getattr(file, p):
                diff.append(p)
        return diff
    
    def copy_to_local(self):
        cmd = [ADB_PATH, '-s', ANDROID_SERIAL, 'pull', '-a', self.remote_path, self.local_path]
        os.makedirs(os.path.dirname(self.local_path), exist_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            print(f"Copied {self.local_path} from Android")
    
    def copy_to_remote(self):
        cmd = [ADB_PATH, '-s', ANDROID_SERIAL, 'push', '-a', self.local_path, self.remote_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            print(f"Copied {self.remote_path} to Android")
    
    def move_to_unhandled(self, unhandled_path):
        dest_dir = os.path.dirname(unhandled_path)
        cmd = [ADB_PATH, '-s', ANDROID_SERIAL, 'shell', f'mkdir -p "{dest_dir}" && mv "{self.remote_path}" "{unhandled_path}"']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            print(f"Moved {self.remote_path} to UNHANDLED")
    
    def __str__(self):
        return f"{self.relative_path}, last_modified: {self.last_modified}, size: {self.size}"


class Folder:
    def __init__(self, relative_path, master_local="", prune=False):
        self.relative_path = relative_path.replace("\\", "/")
        self.remote_path = f"/{REMOTE_ROOT}/{self.relative_path}"
        self.local_path = os.path.join(ANDROID_BACKUP_FOLDER, self.relative_path.replace("/", "\\"))
        if master_local != "":
            if not os.path.exists(master_local):
                raise Exception(f"Path {master_local} does not exist.")
            self.local_path = master_local.replace("/", "\\")
        self.master_local = master_local
        self.prune = prune
        self.files = {}
        self.categories = {}
    
    def get_remote_files(self):
        cmd = [ADB_PATH, '-s', ANDROID_SERIAL, 'shell', 'ls', '-lR', self.remote_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            raise Exception(f"Error: {result.stderr}")
        else:
            folder = ""
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 6:
                    if len(parts) > 0 and parts[0][0] == "/":
                        folder = " ".join(parts).replace(f"/{REMOTE_ROOT}/", "").replace(":", "")
                    continue
                perms, links, owner, group, size, date, time, *filename = parts
                filename = " ".join(filename)
                if "." in filename:
                    full_filename = f"{folder}/{filename}"
                    self.files[full_filename] = self.files.get(full_filename, {"local": None, "remote": None})
                    remote_path = f"/{REMOTE_ROOT}/{full_filename}"
                    local_path = os.path.join(ANDROID_BACKUP_FOLDER, full_filename.replace("/", "\\"))
                    self.files[full_filename]["remote"] = File(self, full_filename, remote_path, local_path, datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M"), int(size))
    
    def get_local_files(self):
        for root, _, files in os.walk(self.local_path):
            for name in files:
                full_path = os.path.join(root, name)
                st = os.stat(full_path)
                size = st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime)
                mtime = mtime.replace(second=0, microsecond=0)
                local_folder = ANDROID_BACKUP_FOLDER if  self.master_local == "" else os.path.dirname(self.master_local)

                full_filename = os.path.relpath(full_path, local_folder).replace("\\", "/")
                remote_path = f"/{REMOTE_ROOT}/{full_filename}"
                local_path = os.path.join(local_folder, full_filename.replace("/", "\\"))
                self.files[full_filename] = self.files.get(full_filename, {"local": None, "remote": None})
                self.files[full_filename]["local"] = File(self, full_filename, remote_path, local_path, mtime, size)
    
    def get_categories(self):
        self.files = {}
        self.get_local_files()
        self.get_remote_files()
        self.categories = {
            "in_sync": [],
            "partial": [],
            "only_local": [],
            "only_remote": []
        }
        for k, v in self.files.items():
            if v['local'] and v['remote']:
                diff = v['local'].get_diff(v['remote'])
                if len(diff):
                    self.categories["partial"].append(k)
                else:
                    self.categories["in_sync"].append(k)
            elif v['local']:
                self.categories["only_local"].append(k)
            elif v['remote']:
                self.categories["only_remote"].append(k)
    
    def get_statistics(self):
        info = {k: {"n": 0, "size": 0} for k in self.categories}
        for f in self.categories["in_sync"]:
            info["in_sync"]["n"] += 1
            info["in_sync"]["size"] += self.files[f]['remote'].size
        for f in self.categories["partial"]:
            info["partial"]["n"] += 1
            info["partial"]["size"] += self.files[f]['remote'].size
        for f in self.categories["only_local"]:
            info["only_local"]["n"] += 1
            info["only_local"]["size"] += self.files[f]['local'].size
        for f in self.categories["only_remote"]:
            info["only_remote"]["n"] += 1
            info["only_remote"]["size"] += self.files[f]['remote'].size
        return info

    def print_files(self, statistics=False):
        if not len(self.categories):
            raise Exception("You must get self.categories first!")
        if not statistics:
            for f in self.categories["in_sync"]:
                print(f"{Fore.GREEN}{self.files[f]['remote']}{Style.RESET_ALL}")
            for f in self.categories["partial"]:
                diff = self.files[f]['local'].get_diff(self.files[f]['remote'])
                string = ", ".join([f"{getattr(self.files[f]['local'], x)} - {getattr(self.files[f]['remote'], x)}" for x in diff])
                print(f"{Fore.LIGHTYELLOW_EX}{f}, {string}{Style.RESET_ALL}")
            for f in self.categories["only_local"]:
                print(f"{Fore.RED}ONLY LOCAL: {self.files[f]['local']}{Style.RESET_ALL}")
            for f in self.categories["only_remote"]:
                print(f"{Fore.RED}ONLY REMOTE: {self.files[f]['remote']}{Style.RESET_ALL}")
        else:
            info = self.get_info()
            parts = [
                ("in_sync", Fore.GREEN),
                ("partial", Fore.LIGHTYELLOW_EX),
                ("only_local", Fore.RED),
                ("only_remote", Fore.RED),
            ]
            for p in parts:
                attr = p[0]
                name = attr.upper().replace("_", " ")
                color = p[1]
                print(f"{color}{name}:\t{info[attr]['n']}\t{scale_bytes(info[attr]['size'])}{Style.RESET_ALL}")

    def migrate_data(self):
        if not len(self.categories):
            raise Exception("You must get self.categories first!")
        if self.master_local != "":
            for f in self.categories["only_remote"] + self.categories["partial"]:
                unhandled_path = "/" + os.path.join(REMOTE_ROOT, self.relative_path + "_unhandled", os.path.relpath(f, self.relative_path)).replace("\\", "/")
                self.files[f]['remote'].move_to_unhandled(unhandled_path)
            
            # dest_dir = "/" + os.path.join(REMOTE_ROOT, self.relative_path).replace("\\", "/") + "/*"
            # cmd = [ADB_PATH, '-s', ANDROID_SERIAL, 'shell', f'rm -r {dest_dir}']
            # subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')

            for f in self.categories["only_local"] + self.categories["partial"]:
                self.files[f]['local'].copy_to_remote()
            
        else:
            for f in self.categories["only_remote"] + self.categories["partial"]:
                self.files[f]['remote'].copy_to_local()
            for f in self.categories["only_local"]:
                self.files[f]['local'].copy_to_remote()


def print_statistics(info: dict):
    parts = [
        ("in_sync", Fore.GREEN),
        ("partial", Fore.LIGHTYELLOW_EX),
        ("only_local", Fore.RED),
        ("only_remote", Fore.RED),
    ]
    print()
    el_to_move = 0
    for i, p in enumerate(parts):
        attr = p[0]
        name = attr.upper().replace("_", " ")
        color = p[1]
        total_n = sum([x[attr]['n'] for x in info.values()])
        el_to_move += total_n if i > 0 else 0
        total_size = sum([x[attr]['size'] for x in info.values()])
        print(f"{color}{name}:\t{total_n}\t{scale_bytes(total_size)}{Style.RESET_ALL}")
    print()
    return el_to_move


folder_map = [
    Folder("Documents", master_local=r"C:\Users\Claudio\Documents\Documents"),
    Folder("Download", prune=True),
    Folder("DCIM"),
    Folder("Pictures"),
    Folder("Movies"),
    Folder("Music"),
    Folder("Audiobooks"),
]


def main():
    total, used, free, percent = parse_sdcard_usage()
    print(f"Memory in use: {scale_bytes(free)}/{scale_bytes(total)}  ->  {percent}")
    
    info = {}
    for f in folder_map:
        f.get_categories()
        info[f.relative_path] = f.get_statistics()
    el_to_move = print_statistics(info)

    if el_to_move == 0:
        return

    info = {}
    files_to_prune = []
    for f in folder_map:
        f.migrate_data()
        f.get_categories()
        info[f.relative_path] = f.get_statistics()
    el_to_move = print_statistics(info)

    if el_to_move == 0:
        print(f"{Fore.GREEN}Synchronization complete!{Style.RESET_ALL}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(f"{Fore.RED}{traceback.format_exc()}{Style.RESET_ALL}")
    time.sleep(5)
