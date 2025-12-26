import wmi
import time
import os
import subprocess

ADB_PATH = os.path.join(os.path.dirname(__file__), "platform-tools", "adb.exe")


def get_devices_ids():
    cmd = [ADB_PATH, 'devices']
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(result.stderr)
    return [x.split(" ")[0].split("\t")[0] for x in result.stdout.strip().split("\n")[1:]]


c = wmi.WMI()
first_devices, first_devices_ids = [], []

input("\nWhile keeping the device disconnected, press ENTER")

usb_devices = c.query("SELECT * FROM Win32_PnPEntity WHERE DeviceID LIKE 'USB\\%'")
for dev in usb_devices:
    first_devices.append(dev)

input("\nConnect the device and press ENTER")
print()

time.sleep(2)


best = {"backup_folder": "", "serial": "", "identifier": ""}
i = 0
for dev_id in get_devices_ids():
    if dev not in first_devices_ids:
        i += 1
        best["serial"] = dev_id
        print(f"Candidate for device SERIAL: {dev_id}")


j = 0
usb_devices = c.query("SELECT * FROM Win32_PnPEntity WHERE DeviceID LIKE 'USB\\%'")
for dev in usb_devices:
    if dev not in first_devices:
        j += 1
        best["identifier"] = dev.DeviceID.split("\\")[1].split("&")[0]
        best["backup_folder"] = f"{dev.Name}"
        print(f"Candidate for USB connection ID: {dev.Name} - {dev.DeviceID}")

if i == 1 and j == 1:
    print(best)
