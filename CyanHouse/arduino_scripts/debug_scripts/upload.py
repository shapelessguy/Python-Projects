import glob
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NETWORK = "192.168.178"
FQBN = "esp32:esp32:esp32:PartitionScheme=default"


def find_arduino_cli():
    return shutil.which("arduino-cli") or r"C:\Program Files\Arduino CLI\arduino-cli.exe"


def find_espota():
    pattern = os.path.join(os.environ["LOCALAPPDATA"], "Arduino15", "packages", "esp32",
                           "hardware", "esp32", "*", "tools", "espota.py")
    found = sorted(glob.glob(pattern))
    if not found:
        sys.exit("espota.py not found, install the esp32 core")
    return found[-1]


def read_password():
    """OTA_PASSWORD from credentials.h if defined, else WIFI_PASSWORD (same rule as CyanDevice.h)."""
    with open(os.path.join(ROOT, "libraries", "CyanDevice", "credentials.h"), encoding="utf-8") as f:
        text = f.read()
    for name in ("OTA_PASSWORD", "WIFI_PASSWORD"):
        m = re.search(rf'^\s*#define\s+{name}\s+"(.*)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    sys.exit("no OTA_PASSWORD or WIFI_PASSWORD in credentials.h")


def find_devices():
    """{name: last octet} for every sketch folder that sets IP_LAST_OCTET."""
    devices = {}
    for name in sorted(os.listdir(ROOT)):
        ino = os.path.join(ROOT, name, f"{name}.ino")
        if not os.path.isfile(ino):
            continue
        with open(ino, encoding="utf-8") as f:
            m = re.search(r"IP_LAST_OCTET\s*=\s*(\d+)", f.read())
        if m:
            devices[name] = int(m.group(1))
    return devices


def flash(name, octet, password):
    dev_path = os.path.join(ROOT, name)
    build_path = os.path.join(dev_path, "build")

    subprocess.run([find_arduino_cli(), "compile", "--fqbn", FQBN,
                    "--output-dir", build_path, dev_path], check=True)

    binary = os.path.join(build_path, "esp32.esp32.esp32", f"{name}.ino.bin")
    if not os.path.isfile(binary):
        binary = os.path.join(build_path, f"{name}.ino.bin")

    subprocess.run([sys.executable, find_espota(), "-i", f"{NETWORK}.{octet}", "-p", "3232",
                    "-a", password, "-f", binary], check=True)


if __name__ == "__main__":
    devices = find_devices()
    wanted = sys.argv[1:] or list(devices)
    unknown = [d for d in wanted if d not in devices]
    if unknown:
        sys.exit(f"unknown device(s) {unknown}, available: {list(devices)}")

    password = read_password()
    for name in wanted:
        print(f"\n=== {name} ({NETWORK}.{devices[name]}) ===")
        flash(name, devices[name], password)
