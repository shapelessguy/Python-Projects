import sys
import os
import time
import traceback
import threading
from colorama import init, Fore, Style
from datetime import datetime
from utils import *
import asyncio
from interfaces import androidInterface, hhdInterface, httpsInterface
from interfaces.https_server.ws_manager import WebSocketManager
from interfaces.https_server.https_server import run_server
init(autoreset=True)

# DEFAULT_LOCAL_ID = "EVA"
# interface_type = "Android" / "HHD"
# interface_id = Samsung / Test / BackupHHD

CONFIGURATION = {
    "headless": True,
    "one_check": False,
    "local_id": "EVA",
    "interfaces": [
        {
            "interface_type": "HTTPS",
            "interface_id": "DLR",
            "interface_args": {
                "local_root": r"C:\Users\shape\Documents",
                "root": r"S:\Documents",
                "folder_map": {
                    "notes": {}
                }
            }
        },
        # {
        #     "interface_type": "HHD",
        #     "interface_id": "Test",
        #     "interface_args": {
        #         "local_root": r"C:\Users\shape\Documents",
        #         "root": r"S:\Documents",
        #         "folder_map": {
        #             "notes": {}
        #         }
        #     }
        # },
        # {
        #     "interface_type": "HHD",
        #     "interface_id": "Test2",
        #     "interface_args": {
        #         "local_root": r"C:\Users\shape\Documents",
        #         "root": r"S:\Documents2",
        #         "folder_map": {
        #             "notes": {}
        #         }
        #     }
        # },
        # {
        #     "interface_type": "Android",
        #     "interface_id": "Samsung",
        #     "interface_args": {
        #         "local_root": r"E:\Video\PhoneMultimedia\SamsungSync",
        #         "android_serial": "RFCY21D9PCK",
        #         "folder_map": {
        #             "Documents": {"master_local": r"C:\Users\shape\Documents\bureaucracy\Documenti"},
        #             "Download": {},
        #             "DCIM": {},
        #             "Pictures": {},
        #             "Movies": {},
        #             "Music": {},
        #         }
        #     }
        # }
    ]
    
}


DEFAULT_SYNC_MD = {"last_sync": 0, "files": {}}

class File:
    folder = None
    relative_path: CPath = None
    remote_path: CPath = None
    local_path: CPath = None
    last_modified: datetime = None
    high_precision: bool = False
    size: int = 0
    
    def __init__(self, folder, relative_path: CPath, remote_path: CPath, local_path: CPath, last_modified, high_precision, size, signal):
        self.folder = folder
        self.relative_path = relative_path
        self.remote_path = remote_path
        self.local_path = local_path
        self.last_modified = last_modified
        self.high_precision = high_precision
        self.size = size
        self.signal = signal
    
    def get_diff(self, file):
        diff = []
        
        hp = self.high_precision and file.high_precision
        lm1 = self.last_modified.replace(second=0, microsecond=0) if not hp else self.last_modified
        lm2 = file.last_modified.replace(second=0, microsecond=0) if not hp else file.last_modified
        this_more_recent = lm1 > lm2
        this_less_recent = lm1 < lm2

        if this_more_recent or this_less_recent:
            diff.append("last_modified")
        # if self.size != file.size:
        #     diff.append("size")
        return diff
    
    def copy_to_local(self, global_stats, from_):
        os.makedirs(os.path.dirname(self.local_path.get_unix_path()), exist_ok=True)
        signal["ui"].execute("set_text", "details_lbl", f"Copying from remote: {self.remote_path.get_unix_path()}")
        self.signal['interface'].copy_file_to_local(self.local_path, self.remote_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        global_stats["in_sync"]["n"] += 1
        global_stats["in_sync"]["size"] += self.size
        self.signal["ui"].execute("set_statistics", global_stats, None)
        print(f"Copied {self.remote_path.get_unix_path()} from remote")
    
    def copy_to_remote(self, global_stats, from_):
        signal["ui"].execute("set_text", "details_lbl", f"Copying from remote: {self.local_path.get_unix_path()}")
        self.signal['interface'].copy_file_to_remote(self.local_path, self.remote_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        global_stats["in_sync"]["n"] += 1
        global_stats["in_sync"]["size"] += self.size
        self.signal["ui"].execute("set_statistics", global_stats, None)
        print(f"Copied {self.local_path.get_unix_path()} to remote")
    
    def remove_from_local(self, global_stats, from_):
        os.makedirs(os.path.dirname(self.local_path.get_unix_path()), exist_ok=True)
        signal["ui"].execute("set_text", "details_lbl", f"Deleting from local: {self.local_path.get_unix_path()}")
        remove_local_file(self.local_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        self.signal["ui"].execute("set_statistics", global_stats, None)
        print(f"Removed {self.local_path.get_unix_path()} from local")
    
    def remove_from_remote(self, global_stats, from_):
        signal["ui"].execute("set_text", "details_lbl", f"Deleting from remote: {self.remote_path.get_unix_path()}")
        self.signal['interface'].delete_file_from_remote(self.remote_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        self.signal["ui"].execute("set_statistics", global_stats, None)
        print(f"Removed {self.remote_path.get_unix_path()} from remote")
    
    def move_to_unhandled(self, unhandled_path: CPath, global_stats, from_):
        self.signal['interface'].move_file_from_remote_to_remote(self.remote_path, unhandled_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        self.signal["ui"].execute("set_statistics", global_stats, None)
        print(f"Moved {self.remote_path.get_unix_path()} to UNHANDLED")
    
    def __str__(self):
        return f"{self.relative_path}, last_modified: {self.last_modified}, size: {self.size}"


class Folder:
    root: CPath = None
    relative_path: CPath = None

    def __init__(self, relative_path: str, master_local="", prune=False, signal={}):
        self.relative_path = CPath(relative_path)
        self.remote_path = self.relative_path.prepend(signal['interface'].root)
        self.local_path = self.relative_path.prepend(signal['interface'].local_root)
        self.sync_md = {}
        self.master_local = CPath(master_local)
        if self.master_local.origin != "":
            if not os.path.exists(self.master_local.get_unix_path()):
                raise Exception(f"Path {self.master_local.get_unix_path()} does not exist")
            self.local_path = self.master_local
        self.prune = prune
        self.signal = signal
        self.files = {}
        self.categories = {}
    
    def get_remote_path_files(self):
        files_to_add = self.signal['interface'].get_remote_files(self.signal, self.remote_path, self.files, remote_root=self.signal['interface'].root)
        for full_filename, local_path, remote_path, date, high_precision, size in files_to_add:
            if full_filename.origin != CPath(self.relative_path.origin).append(SYNC_MD_FILE).origin:
                self.files[full_filename.origin] = self.files.get(full_filename.origin, {"local": None, "remote": None})
                self.files[full_filename.origin]["remote"] = File(self, full_filename, remote_path, local_path, date, high_precision, size, self.signal)
    
    def get_local_path_files(self):
        files_to_add = get_local_files(self.signal, self.local_path, self.relative_path, self.master_local)
        for full_filename, local_path, remote_path, date, high_precision, size in files_to_add:
            if full_filename.origin != CPath(self.relative_path.origin).append(SYNC_MD_FILE).origin:
                self.files[full_filename.origin] = self.files.get(full_filename.origin, {"local": None, "remote": None})
                self.files[full_filename.origin]["local"] = File(self, full_filename, remote_path, local_path, date, high_precision, size, self.signal)
    
    def get_categories(self):
        self.files = {}
        self.categories = {
            "in_sync": [],
            "partial": [],
            "only_local": [],
            "only_remote": []
        }
        self.get_local_path_files()
        self.get_remote_path_files()

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
        
        local_sync_md = get_local_sync_md(self.local_path, self.signal['interface'])
        remote_sync_md = self.signal['interface'].get_remote_sync_md(self.remote_path)
        self.sync_md = local_sync_md
        initialize_md = len(local_sync_md) == 0 or len(remote_sync_md) == 0 or json.dumps(local_sync_md) != json.dumps(remote_sync_md)
        if initialize_md:
            self.sync_md = DEFAULT_SYNC_MD
            self.set_sync()
            local_sync_md = get_local_sync_md(self.local_path, self.signal['interface'])
            remote_sync_md = self.signal['interface'].get_remote_sync_md(self.remote_path)
            if json.dumps(local_sync_md) != json.dumps(remote_sync_md):
                print(len(local_sync_md), len(remote_sync_md))
                raise Exception("Impossible to synchronize folders...")
            self.sync_md = local_sync_md
        else:
            self.set_sync()
    
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
    
    def set_sync(self):
        data = DEFAULT_SYNC_MD
        now = datetime.now().timestamp()
        data["last_sync"] = now
        data["files"] = {f: now for f in self.categories["in_sync"]}
        prev_local_sync_md = self.sync_md

        set_local_sync_md(data, self.local_path, self.signal['interface'])
        try:
            local_file = CPath(os.path.join(self.local_path.get_unix_path(), SYNC_MD_FILE))
            remote_file = CPath(os.path.join(self.remote_path.get_unix_path(), SYNC_MD_FILE))
            self.signal['interface'].copy_file_to_remote(local_file, remote_file)
        except:
            print("Error while updating metadata in local folder")
            set_local_sync_md(prev_local_sync_md, self.local_path, self.signal['interface'])

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

    def migrate_data(self, global_stats):
        if not len(self.categories):
            raise Exception("You must get self.categories first!")
        try:
            self.signal["ui"].execute("set_operation", f"Migrating data for {self.relative_path.get_unix_path()}...", "black")
            if self.master_local.origin != "":
                print(f"Migrating data from MASTER {self.master_local.origin}")

                for f in self.categories["only_remote"]:
                    print("- ", f)

                set_memory_consumption(self.signal)
                if len(self.categories["only_remote"]):
                    print(f"\tMoving {len(self.categories['only_remote'])} files to UNHANDLED...")
                for f in self.categories["only_remote"]:
                    if signal["kill"]:
                        return
                    unhandled_path = CPath(f).relative_to(self.relative_path).prepend(self.relative_path.origin + "_unhandled").prepend(signal['interface'].root)
                    self.files[f]['remote'].move_to_unhandled(unhandled_path, global_stats, from_="only_remote")
                set_memory_consumption(self.signal)

                if len(self.categories["partial"]):
                    print(f"\tMoving {len(self.categories['partial'])} files to UNHANDLED...")
                for f in self.categories["partial"]:
                    if signal["kill"]:
                        return
                    unhandled_path = CPath(f).relative_to(self.relative_path).prepend(self.relative_path.origin + "_unhandled").prepend(signal['interface'].root)
                    self.files[f]['remote'].move_to_unhandled(unhandled_path, global_stats, from_="partial")
                set_memory_consumption(self.signal)

                if len(self.categories["only_local"]):
                    print(f"\tTransferring {len(self.categories['only_local'])} files from master to remote device...")
                for f in self.categories["only_local"]:
                    if signal["kill"]:
                        return
                    self.files[f]['local'].copy_to_remote(global_stats, from_="only_local")

                set_memory_consumption(self.signal)
                if len(self.categories["partial"]):
                    print(f"\tTransferring {len(self.categories['partial'])} files from master to remote device...")
                for f in self.categories["partial"]:
                    if signal["kill"]:
                        return
                    self.files[f]['local'].copy_to_remote(global_stats, from_="partial")
                
            else:
                print(f"Migrating data within {self.relative_path.origin}")

                set_memory_consumption(self.signal)
                if len(self.categories["only_remote"]):
                    print(f"\tTransferring {len(self.categories['only_remote'])} files from remote to local device...")
                for f in self.categories["only_remote"]:
                    if signal["kill"]:
                        return
                    if self.files[f]['remote'].relative_path.origin in self.sync_md["files"]:
                        self.files[f]['remote'].remove_from_remote(global_stats, from_="only_remote")
                        del self.sync_md["files"][self.files[f]['remote'].relative_path.origin]
                    else:
                        self.files[f]['remote'].copy_to_local(global_stats, from_="only_remote")

                set_memory_consumption(self.signal)
                if len(self.categories["partial"]):
                    print(f"\tTransferring {len(self.categories['partial'])} files from remote to local device...")
                for f in self.categories["partial"]:
                    if signal["kill"]:
                        return
                    hp = self.files[f]['local'].high_precision and self.files[f]['remote'].high_precision
                    local_lm = self.files[f]['local'].last_modified
                    remote_lm = self.files[f]['remote'].last_modified
                    local_size = self.files[f]['local'].size
                    remote_size = self.files[f]['remote'].size
                    local_lm = local_lm.replace(second=0, microsecond=0) if not hp else local_lm
                    remote_lm = remote_lm.replace(second=0, microsecond=0) if not hp else remote_lm
                    local_more_recent = local_lm > remote_lm
                    remote_more_recent = local_lm < remote_lm
                    if local_more_recent:
                        self.files[f]['local'].copy_to_remote(global_stats, from_="partial")
                    elif remote_more_recent:
                        self.files[f]['remote'].copy_to_local(global_stats, from_="partial")

                set_memory_consumption(self.signal)
                if len(self.categories["only_local"]):
                    print(f"\tTransferring {len(self.categories['only_local'])} files from local to remote device...")
                for f in self.categories["only_local"]:
                    if signal["kill"]:
                        return
                    if self.files[f]['local'].relative_path.origin in self.sync_md["files"]:
                        self.files[f]['local'].remove_from_local(global_stats, from_="only_local")
                        del self.sync_md["files"][self.files[f]['local'].relative_path.origin]
                    else:
                        self.files[f]['local'].copy_to_remote(global_stats, from_="only_local")

            set_memory_consumption(self.signal)
        except:
            return 1


prev_stats = ""
def print_statistics(signal, info: dict):
    global prev_stats
    parts = [
        ("in_sync", Fore.GREEN),
        ("partial", Fore.LIGHTYELLOW_EX),
        ("only_local", Fore.RED),
        ("only_remote", Fore.RED),
    ]

    el_to_move = 0
    global_stats = {}
    output = "\n"
    for i, p in enumerate(parts):
        attr = p[0]
        name = attr.upper().replace("_", " ")
        color = p[1]
        total_n = sum([x[attr]['n'] for x in info.values()])
        el_to_move += total_n if i > 0 else 0
        total_size = sum([x[attr]['size'] for x in info.values()])
        global_stats[p[0]] = {"n": total_n, "size": total_size}
        output += f"{color}{name}:\t{total_n}\t{scale_bytes(total_size)}{Style.RESET_ALL}\n"
    if prev_stats != output:
        prev_stats = output
        print(output + "\n")

    size_to_reduce = 0
    for i, k in enumerate(global_stats):
        if i > 0:
            size_to_reduce += global_stats[k]["size"]
    signal["ui"].execute("set_statistics", global_stats, size_to_reduce)
    return global_stats, el_to_move


def init_loop(sync_folders, signal):
    while not signal["kill"]:
        init_info = {}
        signal["ui"].execute("set_operation", "Fetching info...", "blue")
        for f in sync_folders:
            f: Folder
            if signal["kill"]:
                return
            f.get_categories()
            init_info[f.relative_path] = f.get_statistics()
        global_stats, el_to_move = print_statistics(signal, init_info)

        if el_to_move > 0:
            post_info = {}
            signal["ui"].execute("set_operation", "Fetching info...", "blue")
            for f in sync_folders:
                if signal["kill"]:
                    return
                if len(f.categories["partial"]) + len(f.categories["only_local"]) + len(f.categories["only_remote"]) == 0:
                    post_info[f.relative_path] = init_info[f.relative_path]
                else:
                    _ = f.migrate_data(global_stats)
                    signal["ui"].execute("set_text", "details_lbl", "")
                    if CONFIGURATION["one_check"]:
                        f.get_categories()
                        post_info[f.relative_path] = f.get_statistics()
            if CONFIGURATION["one_check"]:
                signal["ui"].execute("set_text", "details_lbl", "")
                signal["ui"].execute("set_operation", "Synchronization complete", "green")
                global_stats, el_to_move = print_statistics(signal, post_info)

                if el_to_move == 0:
                    print(f"{Fore.GREEN}Synchronization complete!{Style.RESET_ALL}")
        else:
            if CONFIGURATION["one_check"]:
                signal["ui"].execute("set_operation", "Everything is already synchronized", "green")
            else:
                signal["ui"].execute("set_operation", "Fetching info...", "blue")
        if CONFIGURATION["one_check"] or len(CONFIGURATION["interfaces"]) > 1:
            break
        for _ in range(10):
            if signal["kill"]:
                break
            time.sleep(0.1)


def set_memory_consumption(signal):
    consumption = signal['interface'].get_memory_consumption()
    if consumption:
        used, total, percent = consumption
        signal["ui"].execute("set_text", "used_lbl", scale_bytes(used, 2))
        signal["ui"].execute("set_text", "total_lbl", scale_bytes(total, 2))
        signal["ui"].execute("set_text", "percent_lbl", percent)


def get_interface(interface_str, local_id, interface_id, ws_manager, args):
    if interface_str == "HHD":
        return hhdInterface.HHDInterface(local_id, interface_id, None, args)
    elif interface_str == "Android":
        return androidInterface.AndroidInterface(local_id, interface_id, None, args)
    elif interface_str == "HTTPS":
        return httpsInterface.HTTPSInterface(local_id, interface_id, ws_manager, args)
    else:
        return None


def start_ws_server_thread(signal):
    loop = asyncio.new_event_loop()
    signal["loop"] = loop
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(run_server(signal))
    finally:
        loop.close()


def main(signal):
    MIN_DELAY = 0.5
    try:
        interfaces = []
        for interface in CONFIGURATION["interfaces"]:
            if interface["interface_type"] == "HTTPS" and "ws_manager" not in signal:
                ws_manager = WebSocketManager()
                signal["ws_manager"] = ws_manager
                signal["kill_server"] = asyncio.Event()
                ws_thread = threading.Thread(target=start_ws_server_thread, args=(signal,), daemon=True)
                ws_thread.start()
                while "loop" not in signal:
                    if signal["kill"]:
                        break
                    time.sleep(0.1)
                time.sleep(1)
            interface = get_interface(
                interface["interface_type"],
                CONFIGURATION["local_id"],
                interface["interface_id"],
                signal,
                interface["interface_args"],
            )
            interfaces.append(interface)
        while not signal["kill"]:
            for interface in interfaces:
                if not interface.connected:
                    if interface.device_connected():
                        interface.connected = True
                    else:
                        continue
                try:
                    signal['interface'] = interface
                    init_ = time.time()
                    sync_folders = [Folder(n, signal=signal, **m) for n, m in signal['interface'].folder_map.items()]
                    model_text = signal['interface'].parse_device_info()
                    signal["ui"].execute("set_text", "model_text", model_text)
                    set_memory_consumption(signal)
                    init_loop(sync_folders, signal)

                    time_elapsed = time.time() - init_
                    delay_ticks = int((MIN_DELAY - time_elapsed) * 10) if (MIN_DELAY - time_elapsed) > 0 else 0
                    for _ in range(delay_ticks):
                        if signal["kill"]:
                            break
                        time.sleep(0.1)
                except Exception as e:
                    signal['interface'].connected = False
                    print(traceback.format_exc())
            if CONFIGURATION["one_check"]:
                break
            for _ in range(20):
                if signal["kill"]:
                    break
                time.sleep(0.1)
    except Exception:
        signal["ui"].execute("set_operation", "ERROR: check logs for info", "red")
        print(f"{Fore.RED}{traceback.format_exc()}{Style.RESET_ALL}")
    
    signal["kill_server"].set()
    signal["ui"].execute("set_text", "exit", "Exit")
    for _ in range(100):
        if signal["kill"]:
            break
        time.sleep(0.1)
    signal["kill"] = True
    signal["ui"].execute("quit_app")


try:
    if CONFIGURATION["headless"]:
        from utils import EmptyUI as UI
    else:
        from ui_handle import UI
except:
    from utils import EmptyUI as UI


if __name__ == "__main__":
    form_closed = 1
    sys.argv.append('--no-sandbox')
    try:
        signal = {'kill': False, 'ui': None}
        signal["ui"] = UI()
        signal["ui"].setup_ui(signal)

        global_stats = {
            k: {"n": 0, "size": 0}
            for k in ["in_sync", "partial", "only_local", "only_remote"]
        }
        signal["ui"].execute("set_statistics", global_stats, None)
        signal["ui"].execute("set_operation", "", "black")
        signal["ui"].show_window()

        main_thread = threading.Thread(target=main, args=(signal, ))
        main_thread.start()
    
        form_closed = signal["ui"].wait_for_close(main_thread)
        signal['kill'] = True
    except Exception:
        signal['kill'] = True
        print(traceback.format_exc())
        print("Application crashed.")

    if form_closed == 1:
        sys.exit()
    else:
        sys.exit(form_closed)

