from thread_collection.roomserver import send_to_roomserver
from utils import notify


def send_light_config(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "lights", value)
    if notify_:
        notify(title="Room Server", message=f"Lights {value}", icon="server.png")


def send_audio(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "audio", value)
    if notify_:
        notify(title="Room Server", message=f"Audio System {value}", icon="logitech.png")

def send_top(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "top", value)
    if notify_:
        notify(title="Room Server", message=f"Top light {value}", icon="logitech.png")


def send_tv(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "tv", value)
    if notify_:
        notify(title="Room Server", message=f"TV {value}", icon="tv.png")


def lights_on(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "on", notify_)


def lights_off(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "off", notify_)


def lights_auto(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "auto", notify_)


def top_power(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "w", notify_)


def top_leds(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "rgb", notify_)


def audio_power(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "on/off", notify_)


def tv_power(signal, verbose=False, notify_=True):
    send_tv(signal, verbose, "power", notify_)


def tv_ok(signal, verbose=False, notify_=True):
    send_tv(signal, verbose, "ok", notify_)
