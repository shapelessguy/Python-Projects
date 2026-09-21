"""Room actuator — in-process port of old_roomserver's server.py + actuators.py.

The legacy RoomServer ran as its own Flask process and forwarded validated
commands to an Arduino over a serial port as a raw ASCII string, e.g.
`"topbright+"`, `"lightson"`, `"tvpower"`. The Arduino has since been
replaced by an ESP32 (arduino_scripts/server/server.ino) reached over HTTP,
same as the other standalone ESP32 boards (desk, ...) — so every topic now
goes over HTTP. TOPIC_DEVICE says which device handles each topic;
ESP32_HOSTS resolves a device name to its address. Adding a device means
adding one line to each, no other code changes.

The lights auto on/off schedule (old state.json) is reimplemented here in
Python — the ESP32 sketch itself only understands "on"/"off" for lights
(see server.ino's lightsSpecial), so "auto" is never sent over HTTP; instead
the schedule is saved and a background poller re-evaluates it once a minute
and sends plain on/off. Not ported: the `announce` topic (tied to a separate
Telegram-bot/announcements system) — out of scope here.
"""
import json
import threading
import time
from datetime import datetime, time as dtime
import requests
from api.config import API_DATA_DIR


# Exact allow-lists from the old actuators.py callbacks, plus "strips" (was
# "strip") expanded to the full vocabulary CyanManager's functions/arduino.py
# already had client-side.
TOPIC_COMMANDS: dict[str, set[str]] = {
    "lights": {"on", "off", "auto"},
    "top": {"w", "rgb", "bright+", "bright-", "cold+", "cold-", "col_loop", "col_change", "heart"},
    "strips": {
        "on", "off", "intensity+", "intensity-", "col_loop", "col_loop_intensity",
        "cyan", "violet", "lilac", "orange", "aqua", "blue", "white",
    },
    "tv": {"power", "ok"},
    "audio": {"on/off", "vol+", "vol-", "mute", "level", "effect", "input"},
    "fan": {"on", "off", "mode", "timer", "swing"},
}

# Which physical device handles each topic. "main" (the default for any
# topic not listed) is arduino_scripts/server/server.ino, the ESP32 that
# replaced the serial-connected Arduino.
TOPIC_DEVICE: dict[str, str] = {
    "strips": "desk",
}

# ESP32 device name -> base URL. Boards have fixed IPs (last octet set in each
# sketch's CyanDevice constructor); mDNS is not used. Add new boards here.
ESP32_HOSTS: dict[str, str] = {
    "main": "http://192.168.178.254",
    "desk": "http://192.168.178.253",
}

# arduino_scripts/desk/desk.ino registers its route as "/strip" (singular) —
# unrelated to and unchanged by the API-facing topic name above ("strips"),
# so it's translated back here. server.ino's routes ("lights"/"top"/"tv"/
# "audio") already match their topic names, so no entry is needed for those.
_ESP32_ROUTE = {"strips": "strip"}

# Lights auto-schedule. Only CyanManager's RoomServer thread has time-picker
# fields for "from"/"to" (see its PARAMETERS) — the CyanHouse GUI's/APK's
# "UV AUTO" button is a plain toggle with no time inputs of its own. So the
# window and whether it's currently active are tracked separately: a bare
# "auto" (no set_auto_time) just re-enables whatever window was last saved,
# and a manual on/off only disables it without forgetting that window.
# Persisted to disk so both survive a restart.
_AUTO_STATE_PATH = API_DATA_DIR / "lights_auto.json"
_DEFAULT_AUTO_WINDOW = {"from": "09:00", "to": "20:00"}
_auto_lock = threading.Lock()
_auto_state: dict = {"from": None, "to": None, "enabled": False}
_auto_poller_started = False


class RoomError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def init() -> None:
    """Load the persisted lights-auto schedule and resume its poller if it
    was left enabled."""
    global _auto_state
    try:
        _auto_state = json.loads(_AUTO_STATE_PATH.read_text())
    except Exception:
        _auto_state = {"from": None, "to": None, "enabled": False}
    if _auto_state.get("enabled"):
        _start_auto_poller()


def _send_to_esp32(device: str, topic: str, command: str) -> None:
    host = ESP32_HOSTS.get(device)
    if not host:
        raise RoomError(f"no host configured for device {device!r}", status_code=503)
    route = _ESP32_ROUTE.get(topic, topic)
    try:
        r = requests.get(f"{host}/{route}", params={"cmd": command}, timeout=5)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RoomError(f"{device} unreachable: {e}", status_code=502)


def _in_window(now: dtime, start: dtime, end: dtime) -> bool:
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # overnight window, e.g. 22:00 -> 06:00


def _auto_tick() -> None:
    """Re-apply the saved schedule. Silent no-op if auto isn't enabled or
    the board is briefly unreachable — the next tick catches up."""
    with _auto_lock:
        state = dict(_auto_state)
    if not state.get("enabled") or not state.get("from") or not state.get("to"):
        return
    now = datetime.now().time()
    start = dtime.fromisoformat(state["from"])
    end = dtime.fromisoformat(state["to"])
    try:
        _send_to_esp32("main", "lights", "on" if _in_window(now, start, end) else "off")
    except RoomError:
        pass


def _start_auto_poller() -> None:
    global _auto_poller_started
    if _auto_poller_started:
        return
    _auto_poller_started = True

    def loop() -> None:
        # Schedules are HH:MM (minute granularity), so tick right at each
        # wall-clock minute boundary rather than N seconds after whichever
        # moment auto happened to be turned on — a flat "sleep 60s" drifts
        # by however many seconds into the minute that moment was (e.g.
        # turning auto on at :40:38 would only recheck at :41:38, 38s late).
        while True:
            time.sleep(60 - time.time() % 60)
            try:
                _auto_tick()
            except Exception as e:
                print(f"[room] lights-auto poll error: {e}")

    threading.Thread(target=loop, name="lights-auto-poller", daemon=True).start()


def _set_lights_auto(set_auto_time: dict | None) -> dict:
    global _auto_state
    if set_auto_time and (set_auto_time.get("from") or set_auto_time.get("to")):
        if not set_auto_time.get("from") or not set_auto_time.get("to"):
            raise RoomError("set_auto_time needs both from and to")
        try:
            dtime.fromisoformat(set_auto_time["from"])
            dtime.fromisoformat(set_auto_time["to"])
        except ValueError:
            raise RoomError("set_auto_time.from/to must be HH:MM")
        window = {"from": set_auto_time["from"], "to": set_auto_time["to"]}
    else:
        # No time inputs on this client (the GUI's/APK's plain "auto"
        # toggle) — reuse whatever window was last saved, falling back to a
        # sane default the very first time auto is ever turned on.
        with _auto_lock:
            window = {"from": _auto_state.get("from"), "to": _auto_state.get("to")}
        if not window["from"] or not window["to"]:
            window = dict(_DEFAULT_AUTO_WINDOW)

    state = {**window, "enabled": True}
    with _auto_lock:
        _auto_state = state
    _AUTO_STATE_PATH.write_text(json.dumps(state))
    _start_auto_poller()
    _auto_tick()  # apply immediately instead of waiting up to a minute
    return {"msg": f"lights auto {state['from']}-{state['to']}"}


def _clear_lights_auto() -> None:
    global _auto_state
    with _auto_lock:
        if not _auto_state.get("enabled"):
            return
        _auto_state = {**_auto_state, "enabled": False}
        state = dict(_auto_state)
    _AUTO_STATE_PATH.write_text(json.dumps(state))


def send(topic: str, command: str, set_auto_time: dict | None = None) -> dict:
    """Validate and forward one command to the right ESP32 over HTTP.
    Blocking I/O — call via run_in_threadpool from the router."""
    allowed = TOPIC_COMMANDS.get(topic)
    if allowed is None:
        raise RoomError(f"unknown topic {topic!r}")
    if command not in allowed:
        raise RoomError(f"command {command!r} not recognized for topic {topic!r}")

    if topic == "lights":
        if command == "auto":
            return _set_lights_auto(set_auto_time)
        # A manual on/off is a deliberate override — stop the schedule from
        # flipping it back at the next poll.
        _clear_lights_auto()

    device = TOPIC_DEVICE.get(topic, "main")
    _send_to_esp32(device, topic, command)
    return {"msg": f"{topic} [value={command}] sent to {device}."}
