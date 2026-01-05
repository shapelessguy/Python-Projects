import os
import shutil
import subprocess
import time

from collections import defaultdict
from operator import attrgetter
from screeninfo import get_monitors


class Monitor_:
    def __init__(self, screen, device_name, width, height, x, y):
        self.screen = screen
        self.device_name = device_name
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.id = None
    
    def __str__(self):
        output = f"Screen {self.device_name}: "
        output += f"{self.x}:{self.y} {self.width}x{self.height} - {self.id}"
        return output


def get_screens(signal: dict):
    multimonitor_path = os.path.join(os.path.dirname(__file__), "MultiMonitorTool")
    multimonitor_exe = os.path.join(multimonitor_path, "MultiMonitorTool.exe")
    conf_path = os.path.join(multimonitor_path, "multimonitor.cfg")
    def_conf_path = os.path.join(multimonitor_path, "defaultConfig.cfg")

    try:
        if os.path.exists(conf_path):
            os.remove(conf_path)
            time.sleep(0.1)
    except Exception:
        pass

    subprocess.Popen([multimonitor_exe, "/SaveConfig", conf_path])

    for _ in range(20):
        time.sleep(0.1)
        if os.path.exists(conf_path):
            break

    time.sleep(0.2)

    if os.path.exists(conf_path):
        try:
            shutil.move(conf_path, def_conf_path)
        except shutil.Error:
            raise Exception(f"Error while moving {conf_path} into {def_conf_path}")

    conf_path = def_conf_path
    while not signal["kill"]:
        try:
            return parse_screen_info(conf_path)
        except:
            pass
        time.sleep(2)


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


if __name__ == "__main__":
    screens = get_screens({"kill": False})