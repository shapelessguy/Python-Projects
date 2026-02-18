import subprocess
import pythoncom
import sounddevice as sd
import numpy as np
import pygame
import os
from utils import SV_EXE_PATH, TIMER_EXE, pprint, notify
from pycaw.pycaw import AudioUtilities
from utils import AUDIO_PATH


TEMP_VOLUME = 0.20


volume_ticks = []
for i in range(13):
    volume_ticks.append(i)
for i in range(14, 21, 2):
    volume_ticks.append(i)
for i in range(22, 35, 3):
    volume_ticks.append(i)
for i in range(38, 51, 4):
    volume_ticks.append(i)
for i in range(55, 101, 5):
    volume_ticks.append(i)


def un_mute_volume(volume, new_vol):
    is_muted = volume.GetMute()
    if new_vol < 0.004 and not is_muted:
        volume.SetMute(1, None)
    elif new_vol > 0.004 and is_muted:
        volume.SetMute(0, None)


def get_step(cur_vol, direction):
    global volume_ticks
    cur_vol_int = round(cur_vol * 100, 0)
    next_vol = 0
    for j in range(len(volume_ticks)):
        if direction > 0:
            if j == len(volume_ticks) - 2:
                next_vol = volume_ticks[-1]
                break
            elif volume_ticks[j] <= cur_vol_int < volume_ticks[j+1]:
                next_vol = volume_ticks[j+1]
                break
        elif direction < 0:
            if cur_vol_int == volume_ticks[0]:
                next_vol = volume_ticks[0]
                break
            elif volume_ticks[j] < cur_vol_int <= volume_ticks[j+1]:
                next_vol = volume_ticks[j]
                break
    return (next_vol - cur_vol_int) / 100


def show_alarm(signal, verbose=False):
    subprocess.Popen([TIMER_EXE])


def play_sound(duration=1.5):
    fs = 44100
    t = np.linspace(0, duration, int(fs * duration), False)
    f1 = 950
    f2 = 1050
    wave1 = np.sign(np.sin(2 * np.pi * f1 * t))
    wave2 = np.sign(np.sin(2 * np.pi * f2 * t))
    tone = (wave1 + wave2) / 2
    pulse = (np.sin(2 * np.pi * 5 * t) > 0).astype(float)
    alarm = tone * pulse
    sd.play(alarm, fs)
    sd.wait()


def ring_alarm(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()
    volume.SetMasterVolumeLevelScalar(TEMP_VOLUME, None)
    play_sound()
    volume.SetMasterVolumeLevelScalar(current, None)


def volume_up(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()
    new_vol = round(min(current + get_step(current, +1), 1.0), 2)
    volume.SetMasterVolumeLevelScalar(new_vol, None)
    if verbose:
        pprint("Current volume:", new_vol)
    un_mute_volume(volume, new_vol)


def volume_down(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()
    new_vol = round(max(current + get_step(current, -1), 0.0), 2)
    volume.SetMasterVolumeLevelScalar(new_vol, None)
    if verbose:
        pprint("Current volume:", new_vol)
    un_mute_volume(volume, new_vol)


def play_audio(audio_path):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()

    abs_volume = 0.10
    relative_vol = abs_volume / current
    relative_vol = 1 if relative_vol > 1 else relative_vol
    
    pygame.mixer.init()
    pygame.mixer.music.load(os.path.join(AUDIO_PATH, audio_path))
    pygame.mixer.music.play(1)
    # pygame.mixer.music.play(loops=3, start=10.0)  # start at 10 seconds

    pygame.mixer.music.set_volume(relative_vol)
    pygame.mixer.music.pause()
    pygame.mixer.music.unpause()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)


def switch_to_headphones(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    before = device.FriendlyName
    headphones_name = signal.get_audio_devices()["headphones"]
    subprocess.run([SV_EXE_PATH, '/SetDefault', headphones_name, '1'])
    device = AudioUtilities.GetSpeakers()
    after = device.FriendlyName
    if after != before:
        pprint(f"Switch to {after}")
        notify(title="Default Audio Device", message=f"Switch to: {after}", icon="wh1000.ico")


def switch_to_speakers(signal, verbose=False):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    before = device.FriendlyName
    speakers_name = signal.get_audio_devices()["speakers"]
    subprocess.run([SV_EXE_PATH, '/SetDefault', speakers_name, '1'])
    device = AudioUtilities.GetSpeakers()
    after = device.FriendlyName
    if after != before:
        pprint(f"Switch to {after}")
        notify(title="Default Audio Device", message=f"Switch to: {after}", icon="logitech.ico")
