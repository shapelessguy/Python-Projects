import time
from functions.audio import switch_to_audio_device, split_friendly_name
from functions.monitors import set_primary_screen
from PyQt5.QtWidgets import QLineEdit
from utils import Parameter


NAME = "Devices"
PARAMETERS = {
    "Speakers": Parameter("", QLineEdit),
    "Headphones": Parameter("", QLineEdit),
    "Screen 1": Parameter("", QLineEdit),
    "Screen 2": Parameter("", QLineEdit)
}


def active_output(signal, friendly_name):
    """"speakers" or "headphones" when Windows' default output is the one set
    in that parameter (its name or its device, as the switch takes either),
    None for any other output."""
    devices = signal.thread_managers.get(NAME)
    if devices is None:
        return None
    parts = split_friendly_name(friendly_name)
    for spec in ("Speakers", "Headphones"):
        value = devices.get_param(spec)
        if value and value in parts:
            return spec.lower()
    return None


def switch_to_headphones_():
    global pending_message
    pending_message = ("Audio", "Headphones", "headset.png")


def switch_to_speakers_():
    global pending_message
    pending_message = ("Audio", "Speakers", "speakers.png")


def switch_to_screen_1_():
    global pending_message
    pending_message = ("Screen", "Screen 1", "tv.png")


def switch_to_screen_2_():
    global pending_message
    pending_message = ("Screen", "Screen 2", "tv.png")


def entrypoint(thread_manager):
    global pending_message
    pending_message = None
    while thread_manager.signal.is_alive() and not thread_manager.to_kill:
        if pending_message:
            try:
                device_type, device_spec, icon = pending_message
                pending_message = None
                device_name = thread_manager.get_param(device_spec)
                if device_type == "Audio":
                    switch_to_audio_device(thread_manager.signal, device_name, icon)
                elif device_type == "Screen":
                    set_primary_screen(thread_manager.signal, device_name, icon)
            except:
                pass
        time.sleep(0.1)
