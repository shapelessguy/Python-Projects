import subprocess
import time
import socket
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor, DeviceType


NAME = "PC_CONNECTED_DEVICES"
PARAMETERS = {}
OPENRGB_PORT = 6743


def set_mousepad_color(color):
    global pending_message
    pending_message = (DeviceType.MOUSEMAT, color)


def set_motherboard_color(color):
    global pending_message
    pending_message = (DeviceType.MOTHERBOARD, color)


def is_openrgb_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(("127.0.0.1", OPENRGB_PORT))
            return True
        except ConnectionRefusedError:
            return False


def start_openrgb():
    try:
        openrgb_path = r"C:\Program Files\OpenRGB\OpenRGB.exe"
        cmd = [openrgb_path, "--server", "--startminimized", "--server-port", f"{OPENRGB_PORT}"]
        proc = subprocess.Popen(cmd, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"OpenRGB started on port {OPENRGB_PORT}, process id: {proc.pid}")
    except:
        print(f"OpenRGB on '{openrgb_path}' not found!")


def set_device_color(device_type, color):
    client = OpenRGBClient(address='127.0.0.1', port=OPENRGB_PORT)
    try:
        devices = [d for d in client.devices if d.type == device_type]
        devices[0].set_color(RGBColor(*color))
    finally:
        client.disconnect()


def entrypoint(thread_manager):
    global pending_message
    pending_message = None

    if not is_openrgb_running():
        start_openrgb()

    while thread_manager.signal.is_alive() and not thread_manager.to_kill:
        if pending_message:
            try:
                client = OpenRGBClient(address='127.0.0.1', port=6743)
                devices = [d for d in client.devices if d.type == pending_message[0]]
                target = devices[0]
                color = pending_message[1]
                pending_message = None
                target.set_color(RGBColor(*color))
                client.disconnect()
            except:
                import traceback
                print(traceback.format_exc())
                pass
        time.sleep(0.1)