"""Running the media services only while the media drive is there.

Plex, qBittorrent and pyLoad all live on the drive (MEDIA_DRIVE_READY_DIR,
/mnt/earth/CYAN). Started without it they see an empty folder: Plex marks
the library missing, the downloaders write to the internal disk under the
mount point. So this loop is their switch:

- the partition appears (at boot, or after the dock is replugged) and isn't
  mounted: mount it (`systemctl start mnt-earth.mount`, the fstab entry —
  systemd doesn't remount an fstab entry on hot-plug by itself);
- the folder becomes readable: start the containers, then Plex (in that
  order: starting a container rebuilds Docker's network, and Plex, which
  registers with plex.tv in its first ~15 s and never retries, must not be
  mid-registration then — see EARTH.md);
- the folder is gone: stop them, and keep them stopped;
- what is mounted is not the drive that is plugged in (it was pulled while
  busy, and the unmount failed): stop them, drop the dead mount, and mount
  the drive again.

Started once the drive is ready, they are left alone: stopping Plex by hand
for a while is not undone here. The other direction — the API stopping takes
them down — is the ExecStopPost of cyanhouse-api.service (EARTH.md), which
also runs when this process dies without a clean shutdown.

`systemctl start/stop` of the mount and Plex are allowed to this user by a
polkit rule (EARTH.md); the containers only need the docker group.
"""
import os
import subprocess
import threading
import time
from pathlib import Path

from api.config import (
    MEDIA_DRIVE_CONTAINERS, MEDIA_DRIVE_INTERVAL, MEDIA_DRIVE_MOUNT,
    MEDIA_DRIVE_READY_DIR, MEDIA_DRIVE_SERVICES, MEDIA_DRIVE_UUID,
)

_lock = threading.Lock()
_started = False
_state: dict = {"present": None, "mounted": None, "ready": None, "started": False,
                "since": None, "checked": None, "error": ""}


def _run(cmd: list[str], timeout: int = 120) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}: {(res.stderr or res.stdout).strip() or res.returncode}")


def _systemctl(verb: str, *units: str) -> None:
    _run(["systemctl", "--no-ask-password", verb, *units])


def _mount_unit() -> str:
    return subprocess.run(["systemd-escape", "--path", "--suffix=mount", MEDIA_DRIVE_MOUNT],
                          capture_output=True, text=True, check=True).stdout.strip()


def _device() -> int | None:
    """The drive's partition as a device number, None when it isn't plugged in."""
    try:
        return os.stat(f"/dev/disk/by-uuid/{MEDIA_DRIVE_UUID}").st_rdev
    except FileNotFoundError:
        return None


def _mounted_device() -> int | None:
    """What is mounted at MEDIA_DRIVE_MOUNT, as a device number (the topmost
    mount if several are stacked), from the kernel's mount table rather than
    a stat of the mount point, which can hang on a drive that has just
    dropped off the bus."""
    dev = None
    with open("/proc/self/mountinfo") as f:
        for line in f:
            fields = line.split()
            if fields[4] == MEDIA_DRIVE_MOUNT:
                major, minor = fields[2].split(":")
                dev = os.makedev(int(major), int(minor))
    return dev


def _running_services() -> list[str]:
    return [s for s in MEDIA_DRIVE_SERVICES
            if subprocess.run(["systemctl", "is-active", "--quiet", s]).returncode == 0]


def _running_containers() -> list[str]:
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                         capture_output=True, text=True, timeout=30).stdout.split()
    return [c for c in MEDIA_DRIVE_CONTAINERS if c in out]


def start_all() -> None:
    if MEDIA_DRIVE_CONTAINERS:
        _run(["docker", "start", *MEDIA_DRIVE_CONTAINERS])
    if MEDIA_DRIVE_SERVICES:
        _systemctl("start", *MEDIA_DRIVE_SERVICES)


def stop_all() -> None:
    """Only what is actually running, so a drive that stays away costs two
    status queries a round, not a stop of everything every 10 s."""
    services = _running_services()
    if services:
        _systemctl("stop", *services)
    containers = _running_containers()
    if containers:
        _run(["docker", "stop", *containers])


def check() -> dict:
    problems = []
    device = _device()
    mounted_dev = _mounted_device()
    present = device is not None
    # Unplugged while busy, the old mount survives the drive: systemd's
    # unmount fails, and a replugged drive comes back as a new device under
    # that dead mount. Its folders still look there from the cache, so
    # compare devices, not paths.
    stale = mounted_dev is not None and mounted_dev != device
    mounted = mounted_dev is not None and not stale
    if present and mounted_dev is None:
        try:
            _systemctl("start", _mount_unit())
            mounted = _mounted_device() == device
        except Exception as e:
            problems.append(f"mount: {e}")
    ready = present and mounted and MEDIA_DRIVE_READY_DIR.is_dir()

    if ready != _state["ready"]:
        print(f"drive_watch: {MEDIA_DRIVE_READY_DIR} is "
              + ("there, starting what needs it" if ready else "not there, stopping what needs it"))
        _state.update(since=time.time(), started=False)
    if ready:
        # Retried every round until it goes through (the error is said once).
        if not _state["started"]:
            try:
                start_all()
                _state["started"] = True
            except Exception as e:
                problems.append(f"start: {e}")
    else:
        try:
            stop_all()
        except Exception as e:
            problems.append(f"stop: {e}")
        if stale:
            # Everything that held it is stopped now; detach the dead mount
            # (lazily, EARTH.md) so the next round mounts the drive afresh.
            try:
                _systemctl("stop", _mount_unit())
                print(f"drive_watch: unmounted the dead {MEDIA_DRIVE_MOUNT}")
            except Exception as e:
                problems.append(f"unmount: {e}")

    _state.update(present=present, mounted=mounted, ready=ready, checked=time.time())
    error = "; ".join(problems)
    # Said once, not every round for as long as it lasts.
    if error and error != _state["error"]:
        print(f"drive_watch: {error}")
    _state["error"] = error
    return dict(_state)


def status() -> dict:
    return dict(_state)


def usable(folder: Path) -> bool:
    """Whether a folder can be offered: one on the media drive only while
    the drive is really there (a dead mount still answers from its cache
    for folders read recently), any other simply when it exists."""
    if Path(os.path.abspath(folder)).is_relative_to(MEDIA_DRIVE_MOUNT):
        return _state["ready"] is True and folder.is_dir()
    return folder.is_dir()


def _loop() -> None:
    while True:
        try:
            check()
        except Exception as e:  # never let the thread die
            print(f"drive_watch: {e.__class__.__name__}: {e}")
        time.sleep(max(2, MEDIA_DRIVE_INTERVAL))


def start() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="drive-watch", daemon=True).start()
