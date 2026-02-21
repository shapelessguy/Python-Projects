import subprocess
import sys
import ctypes
from datetime import datetime, time as dtime
from PyQt5.QtWidgets import QCheckBox, QTimeEdit
from utils import wait, Parameter


NAME = "Start&Shutdown"
PARAMETERS = {
    "Mouse Jiggle": Parameter(False, QCheckBox),
    "Inactivity to Shutdown": Parameter("02:00", QTimeEdit),
    "Shutdown from": Parameter("02:00", QTimeEdit),
    "Shutdown to": Parameter("08:00", QTimeEdit),
    "Shutdown": Parameter(False, QCheckBox),
}


def jiggle_mouse():
    ctypes.windll.user32.mouse_event(0x0001, 1, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0001, -1, 0, 0, 0)


def startup(signal):
    print("Startup...")
    app_names_to_start = []
    for _ in range(3):
        started_apps = set(signal.reg_functions.STARTUP.run(app_names_to_start))
        started_apps = set([app.name for app in signal.get_applications() if app.name in started_apps and app.window_props["order"]])
        max_cycles = 10
        c = 0
        while signal.is_alive() and len(started_apps):
            c += 1
            wait(signal, 1000)
            ordered_apps = signal.reg_functions.ORDER.run(started_apps)
            for ordered in ordered_apps:
                started_apps.discard(ordered)
            if c >= max_cycles:
                break
        app_names_to_start = started_apps
        if len(app_names_to_start) == 0:
            break
    signal.reg_functions.ORDER.run_shortcut()


def entrypoint(thread_manager):
    signal = thread_manager.signal
    signal.reg_functions.TURN_ON_MONITORS.run_shortcut()
    if "startup" in sys.argv:
        sys.argv.remove("startup")
        startup(signal)

    pt = signal.reg_functions.GET_MOUSE_POS.run()
    funct_interaction = datetime.now()
    last_pos = (pt.x, pt.y)
    
    while signal.is_alive() and not thread_manager.to_kill:
        thread_params = thread_manager.get_params()
        start_hours, start_minutes = map(int, thread_params["Shutdown from"].split(":"))
        end_hours, end_minutes = map(int, thread_params["Shutdown to"].split(":"))
        inactive_hours, inactive_minutes = map(int, thread_params["Inactivity to Shutdown"].split(":"))
        start = dtime(start_hours, start_minutes)
        end = dtime(end_hours, end_minutes)
        inactive_time = 60 * 60 * inactive_hours + 60 * inactive_minutes
    
        pt = signal.reg_functions.GET_MOUSE_POS.run()
        now = datetime.now()
        if pt.x != last_pos[0] or pt.y != last_pos[1]:
            last_pos = (pt.x, pt.y)
            signal.last_interaction = now
            funct_interaction = now
        else:
            if not (start <= now.time() <= end):
                funct_interaction = now
                if thread_params["Mouse Jiggle"] and not signal.session_locked:
                    diff = (now - signal.last_interaction).total_seconds()
                    if diff > 60:
                        jiggle_mouse()
            elif funct_interaction < signal.last_interaction:
                funct_interaction = signal.last_interaction

        diff = (now - funct_interaction).total_seconds()
        if thread_params["Shutdown"] and diff > inactive_time:
            print("Shutdown triggered!")
            subprocess.run(["shutdown", "/s", "/t", "60"])
            pt_at_shutdown = signal.reg_functions.GET_MOUSE_POS.run()
            for _ in range(59):
                wait(signal, 1000)
                pt = signal.reg_functions.GET_MOUSE_POS.run()
                if pt.x != pt_at_shutdown.x or pt.y != pt_at_shutdown.y:
                    subprocess.run(["shutdown", "/a"])
                    print("Shutdown aborted")
                    break
            funct_interaction = now
        wait(signal, 2000)
    print(f"{thread_manager.name} thread down..")
