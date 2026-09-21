import time
import threading
from openrgb.utils import DeviceType
from thread_collection.pc_connected_devices import set_device_color
from thread_collection.roomserver import NAME as ROOMSERVER_NAME, request_roomserver


ON_COLOR = (0, 180, 255)
OFF_COLOR = (0, 0, 0)
STRIPS_TIMEOUT = 2
# Windows gives an app only a few seconds to answer a session-end message
TOTAL_TIMEOUT = 3


def set_pc_lights(color):
    for device_type in (DeviceType.MOUSEMAT, DeviceType.MOTHERBOARD):
        try:
            set_device_color(device_type, color)
        except Exception as ex:
            print(f"{device_type.name} light failed: {ex.__class__.__name__} - {ex}")


def set_strips(signal, command):
    try:
        params = [x for x in signal.get_threads() if x.name == ROOMSERVER_NAME][0].parameters
        request_roomserver(params, "strips", command, timeout=STRIPS_TIMEOUT)
    except Exception as ex:
        print(f"Strips {command} failed: {ex.__class__.__name__} - {ex}")


def run_all(targets):
    # Blocking on purpose (the caller is a Windows message that must not return before the lights are done),
    # but bounded so a dead RoomServer can not hold the shutdown.
    workers = [threading.Thread(target=t, daemon=True) for t in targets]
    for w in workers:
        w.start()
    deadline = time.time() + TOTAL_TIMEOUT
    for w in workers:
        w.join(max(0, deadline - time.time()))


def lights_off(signal):
    print("Session ending: lights off")
    run_all([lambda: set_pc_lights(OFF_COLOR), lambda: set_strips(signal, "off")])


def lights_on(signal):
    print("Session end cancelled: lights on")
    run_all([lambda: set_pc_lights(ON_COLOR), lambda: set_strips(signal, "on")])
