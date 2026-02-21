from thread_collection.roomserver import send_to_roomserver


def send_light_config(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "lights", value)
    # if notify_:
    #     notify(title="Room Server", message=f"Lights {value}", icon="server.ico")


def send_audio(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "audio", value)
    # if notify_:
    #     notify(title="Room Server", message=f"Lights {value}", icon="server.ico")


def send_tv(signal, verbose, value, notify_):
    send_to_roomserver(signal, verbose, "tv", value)
    # if notify_:
    #     notify(title="Room Server", message=f"Lights {value}", icon="server.ico")


def lights_on(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "on", notify_)


def lights_off(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "off", notify_)


def lights_auto(signal, verbose=False, notify_=True):
    send_light_config(signal, verbose, "auto", notify_)


def audio_power(signal, verbose=False, notify_=True):
    send_audio(signal, verbose, "on/off", notify_)


def tv_power(signal, verbose=False, notify_=True):
    send_tv(signal, verbose, "power", notify_)


def tv_ok(signal, verbose=False, notify_=True):
    send_tv(signal, verbose, "ok", notify_)
