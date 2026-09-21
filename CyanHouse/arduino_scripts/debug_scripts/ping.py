import sys
import time
import requests
from upload import NETWORK, find_devices

devices = find_devices()
wanted = sys.argv[1:] or list(devices)
unknown = [d for d in wanted if d not in devices]
if unknown:
    sys.exit(f"unknown device(s) {unknown}, available: {list(devices)}")

try:
    while True:
        for name in wanted:
            url = f"http://{NETWORK}.{devices[name]}"
            try:
                r = requests.get(f"{url}/ping", timeout=5)
                print(f"{name} ({url}) → {r.status_code}")
            except Exception as e:
                print(f"{name} ({url}) → {e}")
        time.sleep(2)
except KeyboardInterrupt:
    pass
