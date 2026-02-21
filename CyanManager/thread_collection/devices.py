import time
from functions.audio import switch_to_audio_device
from PyQt5.QtWidgets import QLineEdit
from utils import Parameter


NAME = "Devices"
PARAMETERS = {
    "Speakers": Parameter("", QLineEdit),
    "Headphones": Parameter("", QLineEdit)
}


def switch_to_headphones_():
    global pending_message
    pending_message = ("Audio", "Headphones", "wh1000.ico")


def switch_to_speakers_():
    global pending_message
    pending_message = ("Audio", "Speakers", "logitech.ico")


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
                    switch_to_audio_device(device_name, icon)
            except:
                pass
        time.sleep(0.1)
