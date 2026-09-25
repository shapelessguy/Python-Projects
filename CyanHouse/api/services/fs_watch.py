"""The kernel's word that something in a folder changed (Linux inotify,
through ctypes — no dependency): a watch on the folder and on every folder
in it, new ones added as they appear.

`Watch` is the watch itself (image_dims keeps its own loop around one);
`follow()` is the whole job for anyone who only needs to hear about it —
a thread that arms the watch, calls back once a burst of changes has
settled, and arms it again when the folder comes back after going away
(the drive unmounted and mounted again).
"""
import ctypes
import ctypes.util
import os
import select
import struct
import threading
import time
from pathlib import Path
from typing import Callable

_IN = {"MODIFY": 0x2, "ATTRIB": 0x4, "CLOSE_WRITE": 0x8, "MOVED_FROM": 0x40, "MOVED_TO": 0x80,
       "CREATE": 0x100, "DELETE": 0x200, "DELETE_SELF": 0x400, "MOVE_SELF": 0x800,
       "UNMOUNT": 0x2000, "IGNORED": 0x8000, "ISDIR": 0x40000000}
_MASK = (_IN["CLOSE_WRITE"] | _IN["MOVED_FROM"] | _IN["MOVED_TO"] | _IN["CREATE"] | _IN["DELETE"]
         | _IN["DELETE_SELF"] | _IN["MOVE_SELF"] | _IN["ATTRIB"])
_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)


class Watch:
    """inotify on a folder and every folder in it."""

    def __init__(self, root: Path):
        self.root = root
        self.fd = _libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        self.dirs: dict[int, str] = {}
        for dirpath, dirnames, _ in os.walk(root):
            dirnames[:] = [d for d in set(dirnames) if not d.startswith(".")]
            self.add(dirpath)

    def add(self, path: str) -> None:
        wd = _libc.inotify_add_watch(self.fd, os.fsencode(path), _MASK)
        if wd >= 0:
            self.dirs[wd] = path

    def close(self) -> None:
        os.close(self.fd)

    def events(self, timeout: float) -> tuple[bool, bool]:
        """Wait up to `timeout` for events: (something changed, the watch on
        the folder itself is gone — the drive went away)."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False, False
        try:
            buf = os.read(self.fd, 64 * 1024)
        except BlockingIOError:
            return False, False
        changed, lost = False, False
        i = 0
        while i + 16 <= len(buf):
            wd, mask, _cookie, n = struct.unpack_from("iIII", buf, i)
            name = buf[i + 16: i + 16 + n].split(b"\0", 1)[0].decode(errors="replace")
            i += 16 + n
            if mask & (_IN["UNMOUNT"] | _IN["DELETE_SELF"] | _IN["MOVE_SELF"]) and self.dirs.get(wd) == str(self.root):
                lost = True
            if mask & _IN["IGNORED"]:
                gone = self.dirs.pop(wd, None)
                if gone == str(self.root):
                    lost = True
                continue
            if name.startswith("."):
                continue
            changed = True
            # A new folder (made, or moved in) is watched too, and so is
            # everything already inside it.
            if mask & _IN["ISDIR"] and mask & (_IN["CREATE"] | _IN["MOVED_TO"]) and wd in self.dirs:
                for dirpath, dirnames, _ in os.walk(os.path.join(self.dirs[wd], name)):
                    dirnames[:] = [d for d in set(dirnames) if not d.startswith(".")]
                    self.add(dirpath)
        return changed, lost



def follow(root: Path, on_change: Callable[[], None], settle: float = 2.0) -> None:
    """Call `on_change` whenever something under `root` changes, once per
    burst (after `settle` seconds of quiet), from a background thread. Also
    once each time the watch is armed: whatever happened while nothing was
    watching."""
    def loop() -> None:
        while True:
            if not root.is_dir():
                time.sleep(10)
                continue
            try:
                w = Watch(root)
            except OSError as e:
                print(f"fs_watch: cannot watch {root} ({e})")
                return
            on_change()
            try:
                while True:
                    changed, lost = w.events(30)
                    # Let the burst settle: a copy of a thousand files is one call.
                    while changed and not lost:
                        more, lost = w.events(settle)
                        if not more:
                            break
                    if changed:
                        on_change()
                    if lost or not root.is_dir():
                        break
            finally:
                w.close()
            time.sleep(2)

    threading.Thread(target=loop, name=f"fs-watch {root.name}", daemon=True).start()
