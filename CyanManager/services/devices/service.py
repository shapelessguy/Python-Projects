import time
from functions.audio import switch_to_audio_device, get_default_output_id
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


# Windows endpoint id -> "Speakers"/"Headphones": what each switch landed on
output_ids = {}


def active_output():
    """"speakers" or "headphones" when Windows' default output is the device
    a switch to it landed on, None for any other (or none switched to yet)."""
    spec = output_ids.get(get_default_output_id())
    return spec.lower() if spec else None


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
                    device_id = switch_to_audio_device(thread_manager.signal, device_name, icon)
                    if device_id:
                        for k in [k for k, v in output_ids.items() if v == device_spec]:
                            del output_ids[k]
                        output_ids[device_id] = device_spec
                elif device_type == "Screen":
                    set_primary_screen(thread_manager.signal, device_name, icon)
            except:
                pass
        time.sleep(0.1)
