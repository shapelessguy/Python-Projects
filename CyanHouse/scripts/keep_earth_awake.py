#!/usr/bin/env python3
"""Keeps the Earth USB HDD from idling long enough for its dock to sleep.

Written for the Ugreen dock that held Pangea, the drive before Earth: its
USB-SATA bridge had a firmware-level idle timer (~10 min) that renegotiated
its internal USB link when nothing had touched the drive for a while --
usually invisible in dmesg as a harmless "reset SuperSpeed USB device", but
occasionally that renegotiation failed outright and dropped the whole USB
device, requiring a physical replug (see DEPLOY.md, "Mount the Earth drive").
Earth sits in a different dock (ASMedia bridge); touching the drive
comfortably inside that window costs nothing, so it stays on.

Triggered every 5 minutes via crontab (`*/5 * * * *`). A no-op, not an
error, if Earth isn't currently mounted (e.g. mid-troubleshooting). The file
goes in the drive's root, outside EARTH (the share) and CYAN.
"""
import os
import sys
import time
from pathlib import Path

MOUNT = Path("/mnt/earth")
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
