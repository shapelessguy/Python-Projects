"""Room actuator — in-process port of old_roomserver's server.py + actuators.py.

The legacy RoomServer ran as its own Flask process and forwarded validated
commands to an Arduino over a serial port as a raw ASCII string, e.g.
`"topbright+"`, `"lightson"`, `"tvpower"`. This keeps the exact same wire
protocol (so the existing Arduino sketch needs no changes) but runs as a
plain function call inside the CyanHouse backend instead of a second
network hop to a separate service.

Not ported: the lights auto on/off schedule (old state.json) and the
`announce` topic (tied to a separate Telegram-bot/announcements system) —
out of scope here.
"""
import threading
import time
import serial
from api.config import ARDUINO_DEVICE


# Exact allow-lists from the old actuators.py callbacks.
TOPIC_COMMANDS: dict[str, set[str]] = {
    "lights": {"on", "off", "auto"},
    "top": {"w", "rgb", "bright+", "bright-", "cold+", "cold-", "col_loop", "col_change", "heart"},
    "strip": {"on", "off"},
    "tv": {"power", "ok"},
    "audio": {"on/off", "vol+", "vol-", "mute", "level", "effect", "input"},
}

_RECONNECT_SECONDS = 5

_lock = threading.Lock()
_serial: "serial.Serial | None" = None


class RoomError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def init() -> None:
    """Start the background connection attempt. A no-op when no device is
    configured — commands then fail with a clear 503 instead of the app
    hanging at startup waiting for hardware that may not be plugged in."""
    if not ARDUINO_DEVICE or serial is None:
        return
    threading.Thread(target=_connect_loop, daemon=True).start()


def _connect_loop() -> None:
    global _serial
    while True:
        try:
            conn = serial.Serial(
                port=ARDUINO_DEVICE,
                baudrate=9600,
                bytesize=8,
                timeout=1,
                stopbits=serial.STOPBITS_ONE,
            )
        except Exception:
            time.sleep(_RECONNECT_SECONDS)
            continue
        with _lock:
            _serial = conn
        return


def send(topic: str, command: str) -> dict:
    """Validate and forward one command to the Arduino. Blocking (serial I/O)
    — call via run_in_threadpool from the router."""
    global _serial
    allowed = TOPIC_COMMANDS.get(topic)
    if allowed is None:
        raise RoomError(f"unknown topic {topic!r}")
    if command not in allowed:
        raise RoomError(f"command {command!r} not recognized for topic {topic!r}")
    if ARDUINO_DEVICE and serial is None:
        raise RoomError("pyserial not installed", status_code=503)
    if not ARDUINO_DEVICE:
        raise RoomError("Arduino not connected — set ARDUINO_DEVICE in .env", status_code=503)

    with _lock:
        conn = _serial
    if conn is None:
        raise RoomError("Arduino not connected yet — still reconnecting", status_code=503)

    try:
        with _lock:
            conn.write(f"{topic}{command}\r\n".encode("ascii"))
    except Exception as e:
        with _lock:
            _serial = None
        threading.Thread(target=_connect_loop, daemon=True).start()
        raise RoomError(f"serial write failed: {e}", status_code=502)

    return {"msg": f"{topic} [value={command}] sent to arduino."}
