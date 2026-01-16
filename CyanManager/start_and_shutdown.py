import subprocess
import sys
import ctypes
import time
from datetime import datetime, time as dtime
from utils import wait, pprint


def jiggle_mouse():
    ctypes.windll.user32.mouse_event(0x0001, 1, 0, 0, 0)
    ctypes.windll.user32.mouse_event(0x0001, -1, 0, 0, 0)


def startup(signal):
    pprint("Startup...")
    started_apps = set(signal.reg_functions.STARTUP.run())
    started_apps = set([app.name for app in signal.get_applications() if app.name in started_apps and app.window_props["order"]])
    max_cycles = 20
    c = 0
    while signal.is_alive() and len(started_apps):
        c += 1
        wait(signal, 1000)
        ordered_apps = signal.reg_functions.ORDER.run(started_apps)
        for ordered in ordered_apps:
            started_apps.discard(ordered)
        if c >= max_cycles:
            break
    signal.reg_functions.ORDER.run_shortcut()


def monitor_user_activity(signal):
    if "startup" in sys.argv:
        startup(signal)
    signal.reg_functions.TURN_ON_MONITORS.run_shortcut()
    signal.reg_functions.LIGHTS_AUTO.run_shortcut(False)
    pt = signal.reg_functions.GET_MOUSE_POS.run()
    funct_interaction = datetime.now()
    last_pos = (pt.x, pt.y)
    restart_options = signal.get_restart_options()
    start_hours, start_minutes = map(int, restart_options["from"].split(":"))
    end_hours, end_minutes = map(int, restart_options["to"].split(":"))
    inactive_hours, inactive_minutes = map(int, restart_options["inactive_delay"].split(":"))
    start = dtime(start_hours, start_minutes)
    end = dtime(end_hours, end_minutes)
    inactive_time = 60 * 60 * inactive_hours + 60 * inactive_minutes
    while signal.is_alive():
        
        pt = signal.reg_functions.GET_MOUSE_POS.run()
        now = datetime.now()
        if pt.x != last_pos[0] or pt.y != last_pos[1]:
            last_pos = (pt.x, pt.y)
            signal.last_interaction = now
            funct_interaction = now
        else:
            if not (start <= now.time() <= end):
                funct_interaction = now
                if signal.get_restart_options()["mouse_jiggle"]:
                    diff = (now - signal.last_interaction).total_seconds()
                    if diff > 60:
                        jiggle_mouse()
            elif funct_interaction < signal.last_interaction:
                funct_interaction = signal.last_interaction

        diff = (now - funct_interaction).total_seconds()
        if restart_options["active"] and diff > inactive_time:
            pprint("Shutdown triggered!")
            subprocess.run(["shutdown", "/r", "/t", "0"])
            funct_interaction = now
        wait(signal, 1000)


def register_start_and_shutdown_tasks(signal):
    signal.register_thread(name="Start&Shutdown", target=monitor_user_activity, args=(signal,))
