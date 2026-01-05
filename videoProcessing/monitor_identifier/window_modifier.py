import win32gui
import psutil
import win32process
import pywinctl as pwc

import os

# Paths equivalent to your C# static fields
name = os.getlogin()
documents_path = os.path.join(os.path.expanduser("~"), "Documents")
local_code_path = os.path.join(documents_path, "codebase")
app_data_path = os.path.dirname(os.environ.get("APPDATA", "C:\\Users\\Default\\AppData\\Roaming"))
drive_path = os.path.splitdrive(os.environ.get("ProgramFiles", "C:\\Program Files"))[0]
prog86_path = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
prog64_path = os.environ.get("ProgramFiles", "C:\\Program Files")


class Application:
    def __init__(self, name, window_kw, proc_name, path, arguments="", startup=False):
        self.name = name
        self.window_kw = window_kw
        self.proc_name = proc_name
        self.path = path
        self.arguments = arguments
        self.startup = startup

    def __repr__(self):
        return f"Application(name={self.name}, )"


all_apps = [
    Application(
        name="Mattermost",
        window_kw=["Mattermost Desktop App"],
        proc_name="Mattermost",
        path=os.path.join(app_data_path, "Local", "Programs", "mattermost-desktop", "Mattermost.exe")
    ),
    Application(
        name="Mozilla Firefox",
        window_kw=["Mozilla Firefox"],
        proc_name="firefox",
        path=os.path.join(drive_path, "Program Files", "Mozilla Firefox", "firefox.exe"),
    ),
    Application(
        name="Opera",
        window_kw=["Opera"],
        proc_name="opera",
        path=os.path.join(app_data_path, "Local", "Programs", "Opera", "launcher.exe"),
    ),
    Application(
        name="Thunderbird",
        window_kw=[],
        proc_name="thunderbird",
        path=os.path.join(prog64_path, "Mozilla Thunderbird", "thunderbird.exe")
    ),
    Application(
        name="XM4_battery",
        window_kw=[],
        proc_name="Xm4Battery",
        path=os.path.join(local_code_path, "CyanSystemManager", "Xm4Battery-5.11.14",
                          "Xm4Battery", "bin", "Release", "net10.0-windows", "Xm4Battery.exe")
    ),
    Application(
        name="Youtube Music",
        window_kw=["YouTube Music Desktop App"],
        proc_name="youtube-music-desktop-app",
        path=os.path.join(app_data_path, "Local", "youtube_music_desktop_app", "youtube-music-desktop-app.exe"),
    ),
    Application(
        name="Microsoft Teams",
        window_kw=["Microsoft Teams"],
        proc_name="",
        path=os.path.join(app_data_path, "Local", "Microsoft", "Teams", "Update.exe"),
        arguments=" --processStart Teams.exe",
    ),
    Application(
        name="WhatsApp",
        window_kw=["WhatsApp"],
        proc_name="WhatsApp",
        path="",
    ),
    Application(
        name="Telegram",
        window_kw=[],
        proc_name="Telegram",
        path=os.path.join(app_data_path, "Roaming", "Telegram Desktop", "Telegram.exe")
    ),
    Application(
        name="NordVPN",
        window_kw=["NordVPN"],
        proc_name="NordVPN",
        path=os.path.join(prog64_path, "NordVPN", "NordVPN.exe")
    ),
    Application(
        name="QBitTorrent",
        window_kw=["qBittorrent"],
        proc_name="qbittorrent",
        path=os.path.join(prog64_path, "qBittorrent", "qbittorrent.exe")
    ),
    Application(
        name="DeepL",
        window_kw=["DeepL"],
        proc_name="DeepL",
        path=os.path.join(app_data_path, "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "DeepL.lnk"),
        arguments="run --no-wait https://appdownload.deepl.com/windows/0install/deepl.xml",
        startup=True
    ),
    Application(
        name="MSI Afterburner",
        window_kw=["MSI Afterburner", "hardware monitor"],
        proc_name="MSIAfterburner",
        path=os.path.join(prog86_path, "MSI Afterburner", "MSIAfterburner.exe")
    ),
    Application(
        name="Display Fusion",
        window_kw=["Display Fusion"],
        proc_name="",
        path=os.path.join(prog86_path, "DisplayFusion", "DisplayFusion.exe"),
        startup=True,
    ),
    Application(
        name="Discord",
        window_kw=["Discord"],
        proc_name="discord",
        path=os.path.join(app_data_path, "Local", "Discord", "Update.exe"),
    )
]


def find_windows(applications: list[Application]):
    windows = pwc.getAllWindows()
    for win in windows:
        _, pid = win32process.GetWindowThreadProcessId(win.getHandle())
        win.proc_name = psutil.Process(pid).name().replace(".exe", "")
    matches = {}
    
    for a in applications:
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
    return matches


if __name__ == "__main__":
    matches = find_windows(all_apps)
    for m, v in matches.items():
        print(m, v)