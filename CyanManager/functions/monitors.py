import os
import subprocess
import json
from functions.application import get_uwp_apps, get_corrispondences, find_windows
from utils import Monitor_, MULTIMONITOR_EXE_PATH, TEMP_MONITOR_CONF_PATH, wait
from collections import defaultdict
from operator import attrgetter
from screeninfo import get_monitors


EXCLUDE_FROM_DISCOVERY = [
    "explorer",
    "msedgewebview2",
    "ApplicationFrameHost",
    "TextInputHost",
]


# Insert title keywords to filter windows during discovery: if empty you will get all windows
DISCOVER_BY_WIN_TITLE = []
# Insert process's name (like firefox.exe) to filter windows by process: if empty string, you will get all windows
DISCOVER_BY_PROCESS = ""


previous_matches = []
def get_screens(signal, verbose=False):
    global previous_matches
    try:
        if os.path.exists(TEMP_MONITOR_CONF_PATH):
            os.remove(TEMP_MONITOR_CONF_PATH)
    except Exception:
        pass
    subprocess.run([MULTIMONITOR_EXE_PATH, "/SaveConfig", TEMP_MONITOR_CONF_PATH])
    for _ in range(20):
        wait(signal, 100)
        if os.path.exists(TEMP_MONITOR_CONF_PATH):
            break

    monitor_matches = []
    try:
        monitor_matches = parse_screen_info(TEMP_MONITOR_CONF_PATH)
    except:
        print("Parsing screen information unsuccessful.")
        monitor_matches = previous_matches

    if verbose:
        for m in monitor_matches:
            print(f"- _id: {m._id} device_name: {m.device_name} x:{m.x} y:{m.y} width:{m.width} height:{m.height} is_primary:{m.is_primary} name:{m.name}")
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

        if m.screen.x != m.x or m.screen.y != m.y:
            print("Monitor inconsistency detected")

        m.scaling = 1
        if m.screen.width != m.width or m.screen.height != m.height:
            scaling_x = m.width / m.screen.width
            scaling_y = m.height / m.screen.height
            scaling = (scaling_x + scaling_y) / 2
            m.screen.scaling = scaling

        m.screen.device_name = m.device_name
        m.screen._id = m.id
        en_screens.append(m.screen)
    return en_screens


def shutdown_monitors(signal, verbose=False):
    screens = get_screens(signal)
    monitor_names = []
    for s in screens:
        monitor_names.append(s.name)
    subprocess.run([MULTIMONITOR_EXE_PATH, "/TurnOff"] + monitor_names)


def turn_on_monitors(signal, verbose=False):
    screens = get_screens(signal)
    monitor_names = []
    for s in screens:
        monitor_names.append(s.name)
    subprocess.run([MULTIMONITOR_EXE_PATH, "/TurnOn"] + monitor_names)


def point_in_rect(px, py, rx, ry, width, height):
    return (
        rx <= px <= rx + width and
        ry <= py <= ry + height
    )


def get_window_properties(win, screens):
    cm = (win.left + win.width / 2, win.top + win.height / 2)
    primary_screen = [s for s in screens if s.is_primary][0]
    screen = None
    for s in screens:
        if point_in_rect(cm[0], cm[1], s.x, s.y, s.width, s.height):
            screen = s
    if screen is None:
        screen = primary_screen
    return {
        "win_title": win.title,
        "monitor_id": screen._id,
        "x": win.left - screen.x,
        "y": win.top - screen.y,
        "width": win.width,
        "height": win.height,
        "win_state": ("minimized" if win.isMinimized else "maximized" if win.isMaximized else "normal"),
        "proc_name": win.proc.name(),
        "path": win.proc.exe().replace('\\', '/'),
    }


def discover_windows(signal, verbose=False, discover_by_win_title=DISCOVER_BY_WIN_TITLE, discover_by_process=DISCOVER_BY_PROCESS):
    os_windows = find_windows(signal, discover=True)
    screens = get_screens(signal)
    uwp_apps = get_uwp_apps(signal)
    windows_info_windowless = []
    windows_info = []
    for win in os_windows:
        win_info = get_window_properties(win, screens)
        if len(discover_by_win_title) and not any([x in win_info["win_title"] for x in discover_by_win_title]):
            continue
        if discover_by_process != "" and win_info['proc_name'] != discover_by_process:
            continue
        friendly_name = win_info['proc_name'][:-4]
        if friendly_name in EXCLUDE_FROM_DISCOVERY:
            continue
        if win_info["win_title"] == "" or win_info['width'] == 0 or win_info['height'] == 0:
            windows_info_windowless.append(win_info)
        else:
            windows_info.append(win_info)

    if verbose:
        for i, chunk in enumerate([windows_info, windows_info_windowless]):
            if i == 0 and len(chunk):
                print("\n\n BEST MATCHES ---------------------------------- \n")
            elif i == 1 and len(chunk):
                print("\n\n WINDOWLESS ------------------------------------ \n")
            for win_info in chunk:
                clean_name = win_info["proc_name"].lower().replace(".exe", "")
                uwp_names = []
                exact_match = False
                for k, v in uwp_apps.items():
                    if v == win_info['proc_name']:
                        exact_match = True
                        uwp_names.append(k)
                if not exact_match:
                    for k, v in uwp_apps.items():
                        if v.endswith(win_info['proc_name']) or k.replace(" ", "").lower() in clean_name or clean_name in k.replace(" ", "").lower():
                            uwp_names.append(k)
                string = f"\n\t{win_info['proc_name'][:-4]}:\n"
                string += f"\tWindow: title={win_info['win_title']}, monitor_id={win_info['monitor_id']}, "
                string += f"x={win_info['x']}, y={win_info['y']}, width={win_info['width']}, height={win_info['height']}\n"
                string += f"\tproc_name={win_info['proc_name']}, path={win_info['path']}, \n"
                uwp_names = '\n\t'.join(json.dumps(uwp_names, indent=2).split('\n'))
                string += f"\tuwp_names={uwp_names}"
                print(string)

    return windows_info


def get_win_pos(signal, verbose=False):
    screens = get_screens(signal)
    corrispondences = get_corrispondences(signal)

    windows_pos = {}
    for app in signal.get_applications():
        windows_pos[app.name] = app.window_props

    for app, win in corrispondences.items():
        windows_pos[app.name] = get_window_properties(win, screens)
        windows_pos[app.name]["proc_name"] = app.proc_name
        windows_pos[app.name]["proc_type"] = app.proc_type
        windows_pos[app.name]["path"] = app.path

    if verbose:
        for app_name, win_pos in windows_pos.items():
            if win_pos["width"] > 0 and win_pos["height"] > 0:
                print(f"{app_name}: monitor_id={win_pos['monitor_id']}, x={win_pos['x']}, y={win_pos['y']}, width={win_pos['width']}, height={win_pos['height']}")
    return windows_pos


def order(signal, verbose=False, only_app_names=()):
    screens = get_screens(signal)
    corrispondences = get_corrispondences(signal, only_app_names)

    windows_moved = []
    for app, win in corrispondences.items():
        win_props = app.window_props
        monitor_id = win_props["monitor_id"]
        opts = [s for s in screens if s._id == monitor_id]
        if len(opts):
            screen = opts[0]
            try:
                win.restore()
                if win_props["win_state"] not in ["hidden", "minimized"]:
                    win.resizeTo(win_props["width"], win_props["height"])
                    win.moveTo(screen.x + win_props["x"], screen.y + win_props["y"])
                    win.resizeTo(win_props["width"], win_props["height"])
                if win_props["win_state"] == "hidden":
                    win.close()
                elif win_props["win_state"] == "minimized":
                    win.minimize()
                elif win_props["win_state"] == "maximized":
                    win.maximize()
                windows_moved.append(app.name)
            except Exception as e:
                print(f"Exception while moving window for {app.name}: {e}")
    return windows_moved
