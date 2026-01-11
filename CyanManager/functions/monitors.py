import os
import subprocess
import psutil
import win32process
import pywinctl as pwc
import shutil
import time
from utils import Monitor_, MULTIMONITOR_EXE_PATH, TEMP_MONITOR_CONF_PATH, MONITOR_CONF_PATH
from collections import defaultdict
from operator import attrgetter
from screeninfo import get_monitors


def find_windows(signal, verbose=False):
    windows = pwc.getAllWindows()
    for win in windows:
        _, pid = win32process.GetWindowThreadProcessId(win.getHandle())
        win.proc_name = psutil.Process(pid).name().replace(".exe", "")
    matches = {}
    for a in signal.applications:
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
        print("\nFind Windows")
        for k, m in matches.items():
            print(k, m)
        print()
    return matches


def get_screens(signal, verbose=False):
    try:
        if os.path.exists(TEMP_MONITOR_CONF_PATH):
            os.remove(TEMP_MONITOR_CONF_PATH)
            time.sleep(0.1)
    except Exception:
        pass

    subprocess.run([MULTIMONITOR_EXE_PATH, "/SaveConfig", TEMP_MONITOR_CONF_PATH])

    for _ in range(20):
        if os.path.exists(TEMP_MONITOR_CONF_PATH):
            break
        time.sleep(0.1)

    while signal.is_alive():
        try:
            monitor_matches = parse_screen_info(TEMP_MONITOR_CONF_PATH)
            break
        except:
            monitor_matches = []
        time.sleep(1)

    if os.path.exists(TEMP_MONITOR_CONF_PATH):
        try:
            shutil.move(TEMP_MONITOR_CONF_PATH, MONITOR_CONF_PATH)
        except shutil.Error:
            raise Exception(f"Error while moving {TEMP_MONITOR_CONF_PATH} into {MONITOR_CONF_PATH}")

    if verbose:
        print("\nFind Monitors")
        for m in monitor_matches:
            print(f"- _id: {m._id} device_name: {m.device_name} x:{m.x} y:{m.y} width:{m.width} height:{m.height} is_primary:{m.is_primary} name:{m.name}")
        print()
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


def order(signal, verbose=False):
    cur_profile = signal.preferences["current_profile"]
    profile = signal.preferences["all_profiles"][cur_profile]
    windows = find_windows(signal)
    screens = get_screens(signal)
    for app_name, config in profile.items():
        for k, win in windows.items():
            if win is not None and k.name == app_name:
                monitor_id = config["monitor_id"]
                for screen in screens:
                    if screen._id == monitor_id:
                        win.resizeTo(config["width"], config["height"])
                        win.moveTo(screen.x + config["x"], screen.y + config["y"])
