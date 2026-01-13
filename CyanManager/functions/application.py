import os
import wmi
import pythoncom
import subprocess
from utils import pprint


c = None


def create_context():
    global c
    if c is None:
        pythoncom.CoInitialize()
        c = wmi.WMI()


def get_apps_status(signal, verbose=False):
    global c
    create_context()

    applications = signal.get_applications()
    app_exe_names = {a.proc_name: a for a in applications}

    names_q = " OR ".join([f"Name = '{a.proc_name}.exe'" for a in applications])
    query = f""" SELECT * FROM Win32_Process WHERE {names_q} """
    
    for p in c.query(query):
        if p.Name.replace(".exe", "") in app_exe_names:
            app_exe_names[p.Name.replace(".exe", "")].process = p

    if verbose:
        for app in applications:
            pprint(app)
    return applications


def get_uwp_apps(signal, verbose=False):
    import json
    ps_command = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json"
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell failed: {result.stderr}")
    apps = json.loads(result.stdout)
    apps = {x["Name"]: x["AppID"] for x in apps}
    if verbose:
        pprint(json.dumps(apps, indent=2))
    return apps


def startup_applications(signal, verbose=False):
    started_apps = []
    app_name_map = get_uwp_apps(signal, False)
    applications = [x for x in get_apps_status(signal, False) if x.process is None and x.startup]
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
            subprocess.Popen(
                [app.path] + app.arguments.split(),
                cwd=os.path.dirname(app.path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        started_apps.append(app.name)
    return started_apps
