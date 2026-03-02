import subprocess
import time
import socket
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor, DeviceType


NAME = "LEDS"
PARAMETERS = {}
OPENRGB_PORT = 6743


def set_mousepad_color(color):
    global pending_message
    pending_message = color


def is_openrgb_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(("127.0.0.1", OPENRGB_PORT))
            return True
        except ConnectionRefusedError:
            return False


def entrypoint(thread_manager):
    global pending_message
    pending_message = None
    
    if not is_openrgb_running():
        try:
            openrgb_path = r"C:\Program Files\OpenRGB\OpenRGB.exe"
            cmd = [openrgb_path, "--server", "--startminimized", "--server-port", f"{OPENRGB_PORT}"]
            proc = subprocess.Popen(cmd, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"OpenRGB started on port {OPENRGB_PORT}, process id: {proc.pid}")
        except:
            print(f"OpenRGB on '{openrgb_path}' not found!")

    while thread_manager.signal.is_alive() and not thread_manager.to_kill:
        if pending_message:
            try:
                client = OpenRGBClient(address='127.0.0.1', port=6743)
                mousepads = [d for d in client.devices if d.type == DeviceType.MOUSEMAT]
                mousepad = mousepads[0]
                color = pending_message
                pending_message = None
                mousepad.set_color(RGBColor(*color))
            except:
                pass
        time.sleep(0.1)