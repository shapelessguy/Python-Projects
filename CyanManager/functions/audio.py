import subprocess
import pythoncom
import sounddevice as sd
import numpy as np
import pygame
import os
from utils import SV_EXE_PATH, TIMER_EXE, pprint, notify
from pycaw.pycaw import AudioUtilities
from utils import AUDIO_PATH


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


def get_relative_volume(absolute_volume):
    pythoncom.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    current = volume.GetMasterVolumeLevelScalar()

    compensation_speakers = {
        1.0:   0.03,
        0.9:   0.032,
        0.8:   0.038,
        0.7:   0.043,
        0.6:   0.055,
        0.5:   0.09,
        0.4:   0.14,
        0.3:   0.21,
        0.2:   0.45,
        0.1:   1.0,
        0.0:   1.0,
    }
    keys = sorted(compensation_speakers.keys(), reverse=True)
    for i in range(len(keys) - 1):
        upper = keys[i]
        lower = keys[i + 1]
        if lower < current <= upper:
            comp_upper = compensation_speakers[upper]
            comp_lower = compensation_speakers[lower]
            fraction = (current - lower) / (upper - lower)
            interpolated = comp_lower + fraction * (comp_upper - comp_lower)
            modulated = interpolated * absolute_volume * 10
            modulated = 1 if modulated > 1 else modulated
            return modulated
    return 0.5


def play_audio(audio_path, volume, n_loops=1, start_at=0.0):
    pygame.mixer.init()
    pygame.mixer.music.load(os.path.join(AUDIO_PATH, audio_path))
    pygame.mixer.music.play(loops=n_loops, start=start_at)
    pygame.mixer.music.set_volume(get_relative_volume(volume))
    pygame.mixer.music.pause()
    pygame.mixer.music.unpause()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)


    # volume = get_relative_volume(0.1)
def ring_alarm(signal, verbose=False):
    volume = 0.05
    duration = 1.5
    fs = 44100
    t = np.linspace(0, duration, int(fs * duration), False)
    f1 = 1000
    f2 = 100
    wave1 = np.sign(np.sin(2 * np.pi * f1 * t))
    wave2 = np.sign(np.sin(2 * np.pi * f2 * t))
    tone = (wave1 + wave2) / 2
    pulse = 0.35 * (np.sin(2 * np.pi * 5 * t) > 0).astype(float)
    alarm = tone * pulse
    print(volume)
    alarm = alarm * volume
    sd.play(alarm, fs)
    sd.wait()


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
