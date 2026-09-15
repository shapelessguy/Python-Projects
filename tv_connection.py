from vidaa import AsyncVidaaTV
from vidaa.protocol import AuthMethod
import asyncio
from flask import Flask, jsonify, request
import threading
import time
from vidaa import AsyncVidaaTV

tv = AsyncVidaaTV(
    host="192.168.178.61",
    mac_address="d4:f9:21:c2:53:5a",
    use_dynamic_auth=True,
    enable_persistence=True,
    auth_method=AuthMethod.MODERN,
)
tv.connect()

cache = {
    "state": tv.get_state(),
    "volume": tv.get_volume(),
}

def refresh_loop():
    while True:
        time.sleep(10)
        s = tv.get_state()
        v = tv.get_volume()
        if s: cache["state"] = s
        if v: cache["volume"] = v

threading.Thread(target=refresh_loop, daemon=True).start()

app = Flask(__name__)

@app.get("/tv/state")
def get_state():
    return jsonify(cache["state"])

@app.get("/tv/volume")
def get_volume():
    return jsonify(cache["volume"])

@app.post("/tv/volume")
def set_volume():
    tv.set_volume(request.json["volume"])  # 0-100
    return jsonify({"ok": True})

@app.post("/tv/power_on")
def power_on():
    threading.Thread(target=lambda: asyncio.run(tv.async_power_on()), daemon=True).start()
    return jsonify({"ok": True})

@app.post("/tv/power_off")
def power_off():
    threading.Thread(target=lambda: asyncio.run(tv.async_power_off()), daemon=True).start()
    return jsonify({"ok": True})

@app.post("/tv/backlight")
def set_backlight():
    tv.set_backlight(request.json["level"])  # 0-100
    return jsonify({"ok": True})

@app.post("/tv/source")
def set_source():
    tv.set_source(request.json["source"])
    return jsonify({"ok": True})

@app.post("/tv/key")
def send_key():
    tv.send_key(request.json["key"])
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(port=8080)