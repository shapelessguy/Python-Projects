import os
from utils import *


all_apps = [
    Application(
        name="Mattermost",
        window_kw=["Mattermost Desktop App"],
        proc_name="Mattermost",
        path=os.path.join(APP_DATA_PATH, "Local", "Programs", "mattermost-desktop", "Mattermost.exe")
    ),
    Application(
        name="Mozilla Firefox",
        window_kw=["Mozilla Firefox"],
        proc_name="firefox",
        path=os.path.join(C_DRIVE_PATH, "Program Files", "Mozilla Firefox", "firefox.exe"),
    ),
    Application(
        name="Opera",
        window_kw=["Opera"],
        proc_name="opera",
        path=os.path.join(APP_DATA_PATH, "Local", "Programs", "Opera", "launcher.exe"),
    ),
    Application(
        name="Thunderbird",
        window_kw=[],
        proc_name="thunderbird",
        path=os.path.join(PROGRAM_FILES_PATH, "Mozilla Thunderbird", "thunderbird.exe")
    ),
    Application(
        name="XM4_battery",
        window_kw=[],
        proc_name="Xm4Battery",
        path=os.path.join(CODEBASE_PATH, "CyanSystemManager", "Xm4Battery-5.11.14",
                          "Xm4Battery", "bin", "Release", "net10.0-windows", "Xm4Battery.exe")
    ),
    Application(
        name="Youtube Music",
        window_kw=["YouTube Music Desktop App"],
        proc_name="youtube-music-desktop-app",
        path=os.path.join(APP_DATA_PATH, "Local", "youtube_music_desktop_app", "youtube-music-desktop-app.exe"),
    ),
    Application(
        name="Microsoft Teams",
        window_kw=["Microsoft Teams"],
        proc_name="",
        path=os.path.join(APP_DATA_PATH, "Local", "Microsoft", "Teams", "Update.exe"),
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
        path=os.path.join(APP_DATA_PATH, "Roaming", "Telegram Desktop", "Telegram.exe")
    ),
    Application(
        name="NordVPN",
        window_kw=["NordVPN"],
        proc_name="NordVPN",
        path=os.path.join(PROGRAM_FILES_PATH, "NordVPN", "NordVPN.exe")
    ),
    Application(
        name="QBitTorrent",
        window_kw=["qBittorrent"],
        proc_name="qbittorrent",
        path=os.path.join(PROGRAM_FILES_PATH, "qBittorrent", "qbittorrent.exe")
    ),
    Application(
        name="DeepL",
        window_kw=["DeepL"],
        proc_name="DeepL",
        path=os.path.join(APP_DATA_PATH, "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "DeepL.lnk"),
        arguments="run --no-wait https://appdownload.deepl.com/windows/0install/deepl.xml"
    ),
    Application(
        name="MSI Afterburner",
        window_kw=["MSI Afterburner", "hardware monitor"],
        proc_name="MSIAfterburner",
        path=os.path.join(PROGRAM_FILES_X86_PATH, "MSI Afterburner", "MSIAfterburner.exe")
    ),
    Application(
        name="Discord",
        window_kw=["Discord"],
        proc_name="discord",
        path=os.path.join(APP_DATA_PATH, "Local", "Discord", "Update.exe"),
    ),
    Application(
        name="NetMeter Evo",
        window_kw=["NetMeter Evo"],
        proc_name="NetMeterEvo",
        path=r"E:\\Software\\Network\\NetMeterEvo.exe",
    )
]
