import os
import wmi
import pythoncom
import subprocess
import ctypes
import re
import uuid
import json
import psutil
import win32process
import pywinctl as pwc
import traceback
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from utils import CYANSYNC_LOGS_PATH
wintypes.HRESULT = ctypes.c_long


executables = {
    "python": "type:python.exe",
    "chrome": "type:chrome.exe"
}


def assign_exe(processes, app_exe_names):
    for p in processes:
        if p.Name in app_exe_names:
            app_exe_names[p.Name].process = p


def assign_python(processes, app_exe_names):
    for p in processes:
        if "python" in p.Caption.lower():
            for app in app_exe_names[executables["python"]]:
                pass
                if (app.path != "" and p.CommandLine and app.path in p.CommandLine) and app.arguments in p.CommandLine:
                    app.process = p


def assign_chrome(processes, app_exe_names):
    pass


def get_apps_status(signal, verbose=False):
    pythoncom.CoInitialize()
    c = wmi.WMI()

    applications = signal.get_applications()
    win_corrispondences = get_corrispondences(signal)
    app_exe_names = {}
    for a in applications:
        if a.proc_type in executables:
            app_exe_names[executables[a.proc_type]] = app_exe_names.get(executables[a.proc_type], []) + [a]
        else:
            app_exe_names[a.proc_name] = a

    if len(app_exe_names):
        names_q = " OR ".join([f"Name = \"{name.replace('type:', '')}\"" for name in app_exe_names])
        query = f""" SELECT * FROM Win32_Process WHERE {names_q} """
        processes = c.query(query)
        assignments = {
            "exe": assign_exe,
            "python": assign_python,
            "chrome": assign_chrome
        }
        
        for assignment in assignments.values():
            assignment(processes, app_exe_names)
        for a in applications:
            if a.name in [x.name for x in win_corrispondences]:
                a.window = win_corrispondences[[x for x in win_corrispondences if x.name == a.name][0]]

    if verbose:
        for app in applications:
            print(app)
    return applications


def resolve_known_folder(guid_str):
    KF_FLAG_DEFAULT = 0
    SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
    SHGetKnownFolderPath.argtypes = [ctypes.POINTER(ctypes.c_byte), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    SHGetKnownFolderPath.restype = wintypes.HRESULT

    guid_bytes = uuid.UUID(guid_str).bytes_le
    guid = (ctypes.c_byte * 16)(*guid_bytes)
    path_ptr = ctypes.c_wchar_p()

    hr = SHGetKnownFolderPath(guid, KF_FLAG_DEFAULT, None, ctypes.byref(path_ptr))
    if hr != 0:
        pass
    return path_ptr.value


def resolve_all_guids(path_str):
    def repl(match):
        guid_str = match.group(0)
        return resolve_known_folder(guid_str)

    pattern = re.compile(r'\{[0-9A-Fa-f\-]{36}\}')
    resolved = pattern.sub(repl, path_str)
    return os.path.normpath(resolved).replace("\\", "/")


def get_uwp_apps(signal, verbose=False):
    ps_command = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json"
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell failed: {result.stderr}")
    apps = json.loads(result.stdout)
    apps = {x["Name"]: resolve_all_guids(x["AppID"]) for x in apps}
    if verbose:
        print(json.dumps(apps, indent=2))
    return apps


def start_app(signal, app, app_name_map=None):
    if app_name_map is None:    
        app_name_map = get_uwp_apps(signal, False)
    
    try:
        print(f"Starting process -> {[app.path] + app.arguments.split()}")
        if app.proc_type == "exe" and app.path.startswith("app:"):
            app_name = "app:".join(app.path.split("app:")[1:])
            app_id = app_name_map[app_name]
            subprocess.Popen([
                "powershell", "-Command",
                f'Start-Process "shell:AppsFolder\\{app_id}"'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif app.proc_type == "python":
            now = datetime.now()
            curYear = now.strftime("%Y")
            curMonth = now.strftime("%m")
            curDay = now.strftime("%d")
            curHour = now.strftime("%H")
            curMinute = now.strftime("%M")
            if "cyanSync" in app.path:
                logFile = Path(CYANSYNC_LOGS_PATH) / f"{app.name}_{app.arguments}_{curYear}-{curMonth}-{curDay}_{curHour}-{curMinute}.log"
                os.makedirs(os.path.dirname(logFile), exist_ok=True)
                cmd = ["python", app.path, app.arguments, str(logFile)]
                with open(logFile, "w", encoding="utf-8") as log:
                    subprocess.Popen(cmd, stdout=log, stderr=log)
            else:
                cmd = ["python", app.path, app.arguments]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif app.proc_type in ["exe", "chrome"]:
            if app.runas:
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    app.path,
                    app.arguments,
                    os.path.dirname(app.path),
                    1
                )
            else:
                subprocess.Popen(
                    [app.path] + app.arguments.split(),
                    cwd=os.path.dirname(app.path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        return True
    except:
        print(traceback.format_exc())
    return False


def startup_applications(signal, verbose=False, app_names=[]):
    started_apps = []
    app_name_map = get_uwp_apps(signal, False)
    if not len(app_names):
        applications = [x for x in get_apps_status(signal, False) if x.process is None and x.window is None and x.startup]
    else:
        applications = [x for x in get_apps_status(signal, False) if x.process is None and x.window is None and x.name in app_names]
    for app in applications:
        if start_app(signal, app, app_name_map):
            started_apps.append(app.name)
    return started_apps


def kill_application(signal, verbose=False, application=None):
    if verbose:
        print(f"Killing application: {application.name}")
    if application is None:
        return
    applications = [x for x in get_apps_status(signal, False) if (x.process is not None or x.window is not None) and x.name == application.name]
    if not len(applications):
        return
    
    application = applications[0]
    if application.process:
        c = wmi.WMI()
        for process in c.Win32_Process(Name=application.proc_name) + c.Win32_Process(ProcessId=application.process.ProcessId):
            try:
                process.Terminate()
            except:
                pass
    elif application.window:
        import win32gui, win32con
        win_title = application.window.title.lower()
        win32gui.EnumWindows(
            lambda h, _: win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            if win32gui.IsWindowVisible(h)
            and win_title in win32gui.GetWindowText(h).lower()
            else None,
            None
        )


def get_threads_status(signal, verbose=False):
    status = {name: thread.is_alive() for name, thread in signal.threads.items()}
    if verbose:
        for n, s in status.items():
            print(f"Thread {n}: {'ACTIVE' if s else 'DOWN'}")
    return status



def match_app_win(app, win):
    match = None
    if all([v_ in win.title for v_ in app.window_kw]):
        exclude = False
        for kw in app.excluded_kw:
            if kw in win.title:
                exclude = True
                break
        if not exclude:
            match = win
    return match


def find_windows(signal, verbose=False, discover=False):
    windows = pwc.getAllWindows()
    for win in windows:
        _, pid = win32process.GetWindowThreadProcessId(win.getHandle())
        win.proc = psutil.Process(pid)

    found = []
    if discover:
        for win in windows:
            if win.width > 0 and win.height > 0:
                found.append(win)
    else:
        for a in signal.get_applications():
            match = None
            if len(a.window_kw):
                for win in windows:
                    if win.width > 0 and win.height > 0:
                        match = match_app_win(a, win)
                        if match:
                            break
            if not match:
                for win in windows:
                    if win.width > 0 and win.height > 0:
                        if win.proc.name() == a.proc_name:
                            exclude = False
                            for kw in a.excluded_kw:
                                if kw in win.title:
                                    exclude = True
                                    break
                            if not exclude:
                                match = win
                                break
            found.append(match)

    if verbose:
        for win in found:
            print(win)
    return found


def select_exe(win, app):
    return win.proc.name() == app.proc_name


def select_python(win, app):
    if win.proc.name() != "python.exe":
        return False
    match = match_app_win(app, win)
    return match is not None


def select_chrome(win, app):
    if win.proc.name() != "chrome.exe":
        return False
    match = match_app_win(app, win)
    return match is not None


def get_corrispondences(signal, only_app_names=()):
    os_windows = find_windows(signal)
    corrispondences = {}
    for app in signal.get_applications():
        if len(only_app_names) > 0 and app.name not in only_app_names:
            continue
        win_props = app.window_props
        for win in os_windows:
            selected = False
            if win is not None and win_props["order"]:
                selectors = {
                    "exe": select_exe,
                    "python": select_python,
                    "chrome": select_chrome
                }
                for type_, selector in selectors.items():
                    if app.proc_type == type_:
                        selected = selector(win, app)
                        if selected:
                            break
            if selected:
                corrispondences[app] = win
    return corrispondences
