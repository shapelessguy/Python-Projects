import sys
import os
import time
import traceback
import threading
import importlib
from PyQt5 import QtWidgets
from PyQt5 import QtWidgets
from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QApplication
from colorama import init, Fore, Style
from datetime import datetime
from utils import *
from interfaces import androidInterface, hhdInterface
try:
    import frontend
except:
    pass
init(autoreset=True)
ui = None
size_to_reduce, bar_width = 0, 0


class File:
    folder = None
    relative_path: CPath = None
    remote_path: CPath = None
    local_path: CPath = None
    last_modified: datetime = None
    size: int = 0
    
    def __init__(self, folder, relative_path: CPath, remote_path: CPath, local_path: CPath, last_modified, size, signal):
        self.folder = folder
        self.relative_path = relative_path
        self.remote_path = remote_path
        self.local_path = local_path
        self.last_modified = last_modified
        self.size = size
        self.signal = signal
    
    def get_diff(self, file):
        diff = []
        properties = ["last_modified", "size"]
        for p in properties:
            if getattr(self, p) != getattr(file, p):
                diff.append(p)
        return diff
    
    def copy_to_local(self, global_stats, from_):
        os.makedirs(os.path.dirname(self.local_path.get_unix_path()), exist_ok=True)
        self.signal['ui'].details_lbl.setText(f"Copying from remote: {self.remote_path.get_unix_path()}")
        self.signal['interface'].copy_file_to_local(self.local_path, self.remote_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        global_stats["in_sync"]["n"] += 1
        global_stats["in_sync"]["size"] += self.size
        set_statistics(self.signal, global_stats)
        print(f"Copied {self.remote_path.get_unix_path()} from remote")
    
    def copy_to_remote(self, global_stats, from_):
        self.signal['ui'].details_lbl.setText(f"Copying to remote: {self.local_path.get_unix_path()}")
        self.signal['interface'].copy_file_to_remote(self.local_path, self.remote_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        global_stats["in_sync"]["n"] += 1
        global_stats["in_sync"]["size"] += self.size
        set_statistics(self.signal, global_stats)
        print(f"Copied {self.local_path.get_unix_path()} to remote")
    
    def move_to_unhandled(self, unhandled_path: CPath, global_stats, from_):
        self.signal['interface'].move_file_from_remote_to_remote(self.remote_path, unhandled_path)
        global_stats[from_]["n"] -= 1
        global_stats[from_]["size"] -= self.size
        set_statistics(self.signal, global_stats)
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
        for full_filename, local_path, remote_path, date, size in files_to_add:
            self.files[full_filename.origin] = self.files.get(full_filename.origin, {"local": None, "remote": None})
            self.files[full_filename.origin]["remote"] = File(self, full_filename, remote_path, local_path, date, size, self.signal)
    
    def get_local_path_files(self):
        files_to_add = get_local_files(self.signal, self.local_path, self.relative_path, self.master_local)
        for full_filename, local_path, remote_path, date, size in files_to_add:
            self.files[full_filename.origin] = self.files.get(full_filename.origin, {"local": None, "remote": None})
            self.files[full_filename.origin]["local"] = File(self, full_filename, remote_path, local_path, date, size, self.signal)
    
    def get_categories(self):
        self.files = {}
        self.get_local_path_files()
        self.get_remote_path_files()
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

    def migrate_data(self, global_stats):
        if not len(self.categories):
            raise Exception("You must get self.categories first!")
        set_operation(signal, f"Migrating data for {self.relative_path.get_unix_path()}...", "black")
        if self.master_local.origin != "":
            set_memory_consumption(self.signal)
            for f in self.categories["only_remote"]:
                if signal["kill"]:
                    return
                unhandled_path = CPath(f).relative_to(self.relative_path).prepend(self.relative_path.origin + "_unhandled").prepend(signal['interface'].root)
                self.files[f]['remote'].move_to_unhandled(unhandled_path, global_stats, from_="only_remote")
            set_memory_consumption(self.signal)
            for f in self.categories["partial"]:
                if signal["kill"]:
                    return
                unhandled_path = CPath(f).relative_to(self.relative_path).prepend(self.relative_path.origin + "_unhandled").prepend(signal['interface'].root)
                self.files[f]['remote'].move_to_unhandled(unhandled_path, global_stats, from_="partial")
            set_memory_consumption(self.signal)
            for f in self.categories["only_local"]:
                if signal["kill"]:
                    return
                self.files[f]['local'].copy_to_remote(global_stats, from_="only_local")
            set_memory_consumption(self.signal)
            for f in self.categories["partial"]:
                if signal["kill"]:
                    return
                self.files[f]['local'].copy_to_remote(global_stats, from_="partial")
            
        else:
            set_memory_consumption(self.signal)
            for f in self.categories["only_remote"]:
                if signal["kill"]:
                    return
                self.files[f]['remote'].copy_to_local(global_stats, from_="only_remote")
            set_memory_consumption(self.signal)
            for f in self.categories["partial"]:
                if signal["kill"]:
                    return
                self.files[f]['remote'].copy_to_local(global_stats, from_="partial")
            set_memory_consumption(self.signal)
            for f in self.categories["only_local"]:
                if signal["kill"]:
                    return
                self.files[f]['local'].copy_to_remote(global_stats, from_="only_local")
        set_memory_consumption(self.signal)


def set_statistics(signal, global_stats: dict):
    global size_to_reduce
    signal['ui'].sync_n_lbl.setText("#" + str(global_stats["in_sync"]["n"]))
    signal['ui'].sync_size_lbl.setText(scale_bytes(global_stats["in_sync"]["size"]))
    signal['ui'].partial_n_lbl.setText("#" + str(global_stats["partial"]["n"]))
    signal['ui'].partial_size_lbl.setText(scale_bytes(global_stats["partial"]["size"]))
    signal['ui'].local_n_lbl.setText("#" + str(global_stats["only_local"]["n"]))
    signal['ui'].local_size_lbl.setText(scale_bytes(global_stats["only_local"]["size"]))
    signal['ui'].remote_n_lbl.setText("#" + str(global_stats["only_remote"]["n"]))
    signal['ui'].remote_size_lbl.setText(scale_bytes(global_stats["only_remote"]["size"]))

    remaining_width = bar_width
    for element, key in {"partial_bar": "partial", "local_bar": "only_local", "remote_bar": "only_remote"}.items():
        width = int(global_stats[key]["size"] / size_to_reduce * bar_width) if size_to_reduce > 0 else 0
        remaining_width -= width
        for prop in ["setMinimumWidth", "setMaximumWidth"]:
            getattr(getattr(signal['ui'], element), prop)(width)
    signal['ui'].filler_bar.setMinimumWidth(remaining_width)
    signal['ui'].filler_bar.setMaximumWidth(remaining_width)


def set_operation(signal, text, color="black"):
    signal['ui'].operation_lbl.setText(text)
    signal['ui'].operation_lbl.setStyleSheet(f"color: {color}")


def print_statistics(signal, info: dict):
    global size_to_reduce
    parts = [
        ("in_sync", Fore.GREEN),
        ("partial", Fore.LIGHTYELLOW_EX),
        ("only_local", Fore.RED),
        ("only_remote", Fore.RED),
    ]
    print()
    el_to_move = 0
    global_stats = {}
    for i, p in enumerate(parts):
        attr = p[0]
        name = attr.upper().replace("_", " ")
        color = p[1]
        total_n = sum([x[attr]['n'] for x in info.values()])
        el_to_move += total_n if i > 0 else 0
        total_size = sum([x[attr]['size'] for x in info.values()])
        global_stats[p[0]] = {"n": total_n, "size": total_size}
        print(f"{color}{name}:\t{total_n}\t{scale_bytes(total_size)}{Style.RESET_ALL}")

    size_to_reduce = 0
    for i, k in enumerate(global_stats):
        if i > 0:
            size_to_reduce += global_stats[k]["size"]
    set_statistics(signal, global_stats)

    print()
    return global_stats, el_to_move


def init_loop(folder_map, signal):
    init_info = {}
    set_operation(signal, "Fetching info...", "blue")
    for f in folder_map:
        f: Folder
        if signal["kill"]:
            return
        f.get_categories()
        init_info[f.relative_path] = f.get_statistics()
    global_stats, el_to_move = print_statistics(signal, init_info)
    
    if el_to_move > 0:
        post_info = {}
        set_operation(signal, "Fetching info...", "blue")
        for f in folder_map:
            if signal["kill"]:
                return
            if len(f.categories["partial"]) + len(f.categories["only_local"]) + len(f.categories["only_remote"]) == 0:
                post_info[f.relative_path] = init_info[f.relative_path]
            else:
                f.migrate_data(global_stats)
                signal['ui'].details_lbl.setText("")
                f.get_categories()
                post_info[f.relative_path] = f.get_statistics()
        signal['ui'].details_lbl.setText("")
        set_operation(signal, "Synchronization complete", "green")
        global_stats, el_to_move = print_statistics(signal, post_info)

        if el_to_move == 0:
            print(f"{Fore.GREEN}Synchronization complete!{Style.RESET_ALL}")
    else:
        set_operation(signal, "Everything is already synchronized", "green")


def set_memory_consumption(signal):
    used, total, percent = signal['interface'].get_memory_consumption()
    signal['ui'].used_lbl.setText(scale_bytes(used, 2))
    signal['ui'].total_lbl.setText(scale_bytes(total, 2))
    signal['ui'].percent_lbl.setText(percent)


def get_interface(interface_str):
    if interface_str == "HHD":
        return hhdInterface.HHDInterface()
    elif interface_str == "Android":
        return androidInterface.AndroidInterface()
    else:
        return None


def main(signal):
    try:
        signal['interface'] = get_interface(sys.argv[1])
        folder_map = [Folder(n, signal=signal, **m) for n, m in signal['interface'].folder_map.items()]
        model_text = signal['interface'].parse_device_info()
        ui.model_text.setText(model_text)
        set_memory_consumption(signal)

        init_loop(folder_map, signal)
    except Exception:
        set_operation(signal, "ERROR: check logs for info", "red")
        print(f"{Fore.RED}{traceback.format_exc()}{Style.RESET_ALL}")
    
    signal['ui'].exit.setText("Exit")
    for _ in range(100):
        if signal["kill"]:
            break
        time.sleep(0.1)
    signal["kill"] = True
    signal['ui'].app.quit()


def exit_sync(signal):
    exit_lbl = signal['ui'].exit
    signal["kill"] = True
    print(f"Clicked -> {exit_lbl.text()}")
    for _ in range(50):
        if exit_lbl.text() != "Stop sync":
            break
        time.sleep(0.1)
    app.quit()


class WindowDragFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._drag_pos = None

    def eventFilter(self, obj, event):
        if obj is self.window:
            if event.type() == event.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPos() - self.window.frameGeometry().topLeft()
                return True

            elif event.type() == event.MouseMove and event.buttons() & Qt.LeftButton and self._drag_pos:
                self.window.move(event.globalPos() - self._drag_pos)
                return True

            elif event.type() == event.MouseButtonRelease:
                self._drag_pos = None
                return True

        return False


if __name__ == "__main__":
    ui_files = ['frontend']
    ui_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.ui') for x in ui_files]
    py_paths = [os.path.join(os.path.dirname(os.path.realpath(__file__)), x + '.py') for x in ui_files]
    for i in range(len(ui_paths)):
        ui_path = ui_paths[i]
        py_path = py_paths[i]
        if os.path.exists(ui_path):
            os.system(f'pyuic5 -x {ui_path} -o {py_path}')
            print(f'pyuic5 -x {ui_path} -o {py_path}')
    importlib.reload(frontend)

    sys.argv.append('--no-sandbox')
    app = QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    
    form_closed = 1
    try:
        ui = frontend.Ui_MainWindow()
        ui.main_window = MainWindow
        ui.main_window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        drag_filter = WindowDragFilter(MainWindow)
        MainWindow.installEventFilter(drag_filter)

        signal = {'kill': False, 'ui': ui}
        ui.setupUi(MainWindow)
        ui.app = app
        ui.exit.clicked.connect(lambda _=False: exit_sync(signal))
        
        for p, p_text in {"sync": "Objects in sync", "partial": "Objects with conflicting metadata",
                  "local": "Objects available only on the current system", "remote": "Objects available only on the remote device"}.items():
            for el_name, el_text in {"icon": "", "n_lbl": ": absolute number", "size_lbl": ": total size"}.items():
                tooltip_text = f"{p_text}{el_text}"
                object_id = f"{p}_{el_name}"
                getattr(ui, object_id).setToolTip(tooltip_text)

        global_stats = {
            k: {"n": 0, "size": 0}
            for k in ["in_sync", "partial", "only_local", "only_remote"]
        }
        set_statistics(signal, global_stats)
        set_operation(signal, "")
        
        ui.model_text.setText("")
        ui.details_lbl.setText("")

        width = 468
        height = 210
        bar_width = ui.bar.width()
        
        MainWindow.resize(width, height)
        screen_geometry = app.primaryScreen().availableGeometry()
        x = screen_geometry.width() - width - 4
        y = screen_geometry.height() - height - 1
        MainWindow.move(x, y)
        MainWindow.show()

        main_thread = threading.Thread(target=main, args=(signal, ))
        main_thread.start()
    
        form_closed = app.exec_()
        signal['kill'] = True
    except Exception:
        signal['kill'] = True
        print(traceback.format_exc())
        print("Application crashed.")

    if form_closed == 1:
        sys.exit()
    else:
        sys.exit(form_closed)

