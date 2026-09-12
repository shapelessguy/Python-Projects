import requests
import time

DEVICES = [
    "http://desk.local",
    "http://server.local",
    # add more here
]

while True:
    for device in DEVICES:
        try:
            r = requests.get(f"{device}/ping", timeout=5)
            print(f"{device} → {r.status_code}")
        except Exception as e:
            print(f"{device} → {e}")
    time.sleep(2)