import os
import wmi
import pythoncom
import subprocess
import ctypes
import re
import uuid
import json
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from utils import pprint, CYANSYNC_LOGS_PATH
wintypes.HRESULT = ctypes.c_long


def get_apps_status(signal, verbose=False):
    pythoncom.CoInitialize()
    c = wmi.WMI()

    applications = signal.get_applications()
    app_exe_names = {}
    for a in applications:
        if "python:" in a.proc_name:
            app_exe_names["python.exe"] = app_exe_names.get("python.exe", []) + [a]
        app_exe_names[a.proc_name] = a

    if len(app_exe_names):
        names_q = " OR ".join([f"Name = \"{name}\"" for name in app_exe_names])
        query = f""" SELECT * FROM Win32_Process WHERE {names_q} """
        for p in c.query(query):
            if "python" in p.Caption.lower():
                for app in app_exe_names["python.exe"]:
                    if app.path in p.CommandLine and app.arguments in p.CommandLine:
                        app.process = p
            elif p.Name in app_exe_names:
                app_exe_names[p.Name].process = p

    if verbose:
        for app in applications:
            pprint(app)
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
        pprint(json.dumps(apps, indent=2))
    return apps


def startup_applications(signal, verbose=False, application=None):
    started_apps = []
    app_name_map = get_uwp_apps(signal, False)
    if application is None:
        applications = [x for x in get_apps_status(signal, False) if x.process is None and x.startup]
    else:
        applications = [x for x in get_apps_status(signal, False) if x.process is None and x.name == application.name]
    for app in applications:
        pprint(f"Starting process -> {[app.path] + app.arguments.split()}")
        if app.path.startswith("app:"):
            app_name = "app:".join(app.path.split("app:")[1:])
            app_id = app_name_map[app_name]
            subprocess.Popen([
                "powershell", "-Command",
                f'Start-Process "shell:AppsFolder\\{app_id}"'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if app.proc_name.startswith("python:"):
                app_name = "python:".join(app.proc_name.split("python:")[1:])
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
            else:
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
        started_apps.append(app.name)
    return started_apps


def kill_application(signal, verbose=False, application=None):
    print("Killing")
    if application is None:
        return
    applications = [x for x in get_apps_status(signal, False) if x.process is not None and x.name == application.name]
    if not len(applications):
        return
    
    c = wmi.WMI()
    for process in c.Win32_Process(Name=applications[0].proc_name):
        try:
            process.Terminate()
        except:
            pass
    print("4")


def get_threads_status(signal, verbose=False):
    status = {name: thread.is_alive() for name, thread in signal.threads.items()}
    if verbose:
        for n, s in status.items():
            pprint(f"Thread {n}: {'ACTIVE' if s else 'DOWN'}")
    return status
