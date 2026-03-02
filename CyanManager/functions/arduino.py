from thread_collection.roomserver import send_to_roomserver
from utils import notify


def send_light_config(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "lights", value)
    if notify_:
        notify(signal, title="Room Server", message=f"Lights {value}", icon="server.png")

# ---------------------------------------------------------

def send_audio(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "audio", value)
    if notify_:
        notify(signal, title="Room Server", message=f"Audio System {value}", icon="audio_system.png")

def send_top(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "top", value)
    if notify_:
        notify(signal, title="Room Server", message=f"Top light {value}", icon="lights.png")

def send_tv(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "tv", value)
    if notify_:
        notify(signal, title="Room Server", message=f"TV {value}", icon="tv.png")

# ---------------------------------------------------------

def lights_on(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "on", notify_)

def lights_off(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "off", notify_)

def lights_auto(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "auto", notify_)

# ---------------------------------------------------------

def top_power(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "w", notify_)

def top_leds(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "rgb", notify_)

def top_bright_plus(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "bright+", notify_)

def top_bright_minus(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "bright-", notify_)

def top_cold_plus(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "cold+", notify_)

def top_cold_less(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "cold-", notify_)

def top_col_loop(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "col_loop", notify_)

def top_col_change(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "col_change", notify_)

def top_heart(signal, verbose=False, notify_=True):
    send_top(signal, verbose, "heart", notify_)

# ---------------------------------------------------------

def audio_power(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "on/off", notify_)

def audio_plus(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "vol+", notify_)

def audio_minus(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "vol-", notify_)

def audio_level(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "level", notify_)

def audio_effect(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "effect", notify_)

# ---------------------------------------------------------

def tv_power(signal, verbose=False, notify_=True):
    send_tv(signal, verbose, "power", notify_)

def tv_ok(signal, verbose=False, notify_=True):
    send_tv(signal, verbose, "ok", notify_)
