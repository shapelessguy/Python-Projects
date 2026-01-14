import os
import subprocess
import psutil
import win32process
import pywinctl as pwc
import shutil
import ctypes
from utils import Monitor_, MULTIMONITOR_EXE_PATH, TEMP_MONITOR_CONF_PATH, MONITOR_CONF_PATH, wait, pprint
from collections import defaultdict
from operator import attrgetter
from screeninfo import get_monitors


def find_windows(signal, verbose=False):
    windows = pwc.getAllWindows()
    for win in windows:
        _, pid = win32process.GetWindowThreadProcessId(win.getHandle())
        win.proc_name = psutil.Process(pid).name().replace(".exe", "")
    matches = {}
    for a in signal.get_applications():
        match = None 
        if len(a.window_kw):
            for win in windows:
                if all([v_ in win.title for v_ in a.window_kw]):
                    match = win
                    break
        else:
            for win in windows:
                if win.proc_name == a.proc_name:
                    match = win
                    break
        matches[a] = match
    if verbose:
        pprint("\nFind Windows")
        for k, m in matches.items():
            pprint(k, m)
        pprint()
    return matches


def get_screens(signal, verbose=False):
    try:
        if os.path.exists(TEMP_MONITOR_CONF_PATH):
            os.remove(TEMP_MONITOR_CONF_PATH)
            wait(signal, 100)
    except Exception:
        pass

    subprocess.run([MULTIMONITOR_EXE_PATH, "/SaveConfig", TEMP_MONITOR_CONF_PATH])

    for _ in range(20):
        if os.path.exists(TEMP_MONITOR_CONF_PATH):
            break
        wait(signal, 100)

    while signal.is_alive():
        try:
            monitor_matches = parse_screen_info(TEMP_MONITOR_CONF_PATH)
            break
        except:
            monitor_matches = []
        wait(signal, 1000)

    if os.path.exists(TEMP_MONITOR_CONF_PATH):
        try:
            shutil.move(TEMP_MONITOR_CONF_PATH, MONITOR_CONF_PATH)
        except shutil.Error:
            raise Exception(f"Error while moving {TEMP_MONITOR_CONF_PATH} into {MONITOR_CONF_PATH}")

    if verbose:
        pprint("\nFind Monitors")
        for m in monitor_matches:
            pprint(f"- _id: {m._id} device_name: {m.device_name} x:{m.x} y:{m.y} width:{m.width} height:{m.height} is_primary:{m.is_primary} name:{m.name}")
        pprint()
    return monitor_matches


def parse_screen_info(info_path):
    lines = []
    with open(info_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    monitors_data = []
    current = []
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            if current:
                monitors_data.append(current)
            current = []
        else:
            if current is not None and "=" in line:
                current.append(line.split("=", 1)[1])
    if current:
        monitors_data.append(current)

    temp_monitors = []
    screens = get_monitors()

    for monitor_cfg in monitors_data:
        try:
            device_name = monitor_cfg[1].split("\\")[1]
        except IndexError:
            device_name = monitor_cfg[1]

        try:
            width = int(monitor_cfg[3])
            height = int(monitor_cfg[4])
            x = int(monitor_cfg[8])
            y = int(monitor_cfg[9])
        except (IndexError, ValueError):
            width = height = x = y = 0

        screen = next((s for s in screens if s.name == monitor_cfg[0]), None)
        temp_monitors.append(Monitor_(screen, device_name, width, height, x, y))

    temp_monitors.sort(key=attrgetter("x"))

    name_freq = defaultdict(int)
    en_screens = []
    for m in temp_monitors:
        name_freq[m.device_name] += 1
        if name_freq[m.device_name] == 1:
            m.id = m.device_name
        else:
            m.id = f"{m.device_name}({name_freq[m.device_name]})"

        if m.screen.x != m.x or m.screen.y != m.y or m.screen.width != m.width or m.screen.height != m.height:
            raise("Monitor inconsistency detected")
        m.screen.device_name = m.device_name
        m.screen._id = m.id
        en_screens.append(m.screen)
    return en_screens


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


pt = POINT()
def get_mouse_position(signal, verbose=False):
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt


def shutdown_monitors(signal, verbose=False):
    screens = get_screens(signal)
    monitor_names = []
    for s in screens:
        if s.device_name != "HECB350":
            monitor_names.append(s.name)
    subprocess.run([MULTIMONITOR_EXE_PATH, "/TurnOff"] + monitor_names)


def turn_on_monitors(signal, verbose=False):
    screens = get_screens(signal)
    monitor_names = []
    for s in screens:
        if s.device_name != "HECB350":
            monitor_names.append(s.name)
    subprocess.run([MULTIMONITOR_EXE_PATH, "/TurnOn"] + monitor_names)


def order(signal, verbose=False, specific_apps=()):
    os_windows = find_windows(signal)
    screens = get_screens(signal)

    windows_moved = []
    for app in signal.get_applications():
        if len(specific_apps) > 0 and app.name not in specific_apps:
            continue
        app_name = app.name
        win_props = app.window_props
        for k, win in os_windows.items():
            if win is not None and k.name == app_name and win_props["order"]:
                monitor_id = win_props["monitor_id"]
                for screen in screens:
                    if screen._id == monitor_id:
                        win.resizeTo(win_props["width"], win_props["height"])
                        win.moveTo(screen.x + win_props["x"], screen.y + win_props["y"])
                        if win_props["win_state"] == "normal":
                            win.restore()
                        elif win_props["win_state"] == "hidden":
                            win.close()
                        elif win_props["win_state"] == "minimized":
                            win.minimize()
                        windows_moved.append(app_name)
    return windows_moved
