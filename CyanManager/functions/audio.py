import os
import subprocess
import pythoncom
from utils import SV_EXE_PATH, ICONS_FOLDER_PATH
from pycaw.pycaw import AudioUtilities
from plyer import notification


def volume_up(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()
    new_vol = round(min(current + 0.01, 1.0), 2)
    volume.SetMasterVolumeLevelScalar(new_vol, None)
    # print("Current volume:", new_vol)
    if new_vol > 0.004:
        is_muted = volume.GetMute()
        if is_muted:
            volume.SetMute(0, None)


def volume_down(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()
    new_vol = round(max(current - 0.01, 0.0), 2)
    volume.SetMasterVolumeLevelScalar(new_vol, None)
    # print("Current volume:", new_vol)
    if new_vol < 0.004:
        is_muted = volume.GetMute()
        if not is_muted:
            volume.SetMute(1, None)


def switch_to_headphones(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    before = device.FriendlyName
    subprocess.run([SV_EXE_PATH, '/SetDefault', 'Headphones', '1'])
    device = AudioUtilities.GetSpeakers()
    after = device.FriendlyName
    if after != before:
        print(f"Switch to {after}")
        notification.notify(
            title="Default Audio Device",
            app_name="CyanSystemManager",
            message=f"Switch to: {after}",
            app_icon=os.path.join(ICONS_FOLDER_PATH, "wh1000.ico"),
            timeout=2
        )


def switch_to_speakers(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    before = device.FriendlyName
    subprocess.run([SV_EXE_PATH, '/SetDefault', 'SPDIF-Out', '1'])
    device = AudioUtilities.GetSpeakers()
    after = device.FriendlyName
    if after != before:
        print(f"Switch to {after}")
        notification.notify(
            title="Default Audio Device",
            app_name="CyanSystemManager",
            message=f"Switch to: {after}",
            app_icon=os.path.join(ICONS_FOLDER_PATH, "logitech.ico"),
            timeout=2
        )
