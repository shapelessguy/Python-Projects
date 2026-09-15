#!/usr/bin/env python3
"""Keeps the Pangea USB HDD from tripping its dock's auto-sleep timer.

The Ugreen dock's USB-SATA bridge appears to have a firmware-level idle
timer (~10 min) that renegotiates its internal USB link when nothing has
touched the drive for a while -- usually invisible in dmesg as a harmless
"reset SuperSpeed USB device", but occasionally that renegotiation fails
outright and drops the whole USB device, requiring a physical replug
(see DEPLOY.md, "Mount the Pangea drive"). Touching the drive comfortably
inside that window keeps it from ever idling long enough to trigger it.

Triggered every 5 minutes via crontab (`*/5 * * * *`). A no-op, not an
error, if Pangea isn't currently mounted (e.g. mid-troubleshooting).
"""
import os
import sys
import time
from pathlib import Path

MOUNT = Path("/mnt/pangea")
KEEPALIVE_FILE = MOUNT / ".keepalive"


def main() -> int:
    if not MOUNT.is_mount():
        return 0

    fd = os.open(KEEPALIVE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o664)
    try:
        os.write(fd, str(time.time()).encode())
        os.fsync(fd)  # force the write past the page cache onto the actual disk
    finally:
        os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
