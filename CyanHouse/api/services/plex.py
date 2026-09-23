"""Telling Plex when a film lands in (or leaves) one of its libraries.

Plex's own watching does notice a folder appearing, but the scan it then
starts skips folders whose modification time looks unchanged — and a folder
moved on the NTFS library drive keeps its old one, so a film moved or
remuxed into a library would not show up until someone pressed "Scan
Library Files". Asking Plex to scan the exact folder does work, and is
cheap: a partial scan of one film's folder rather than of the library.

Everything here is best effort and in the background. A move or a remux has
already succeeded by the time Plex is told; Plex being down, or no
PLEX_TOKEN in secrets.json, only means it is not told.

The libraries are Plex's own list (which folder belongs to which section),
fetched from it and cached, so nothing needs configuring per library.
"""
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from api.config import PLEX_TOKEN, PLEX_URL

# Plex's list of libraries changes rarely; asked again after this long.
SECTIONS_TTL = 300
# File operations come in bursts (a remux moves the file, then clears the
# source): collected for this long and sent as one scan per folder.
SETTLE_SECONDS = 2

_lock = threading.Lock()
_pending: set[Path] = set()
_timer: threading.Timer | None = None
_sections: list[tuple[str, Path]] = []
_sections_at = 0.0


def _get(endpoint: str, **params) -> requests.Response:
    r = requests.get(PLEX_URL + endpoint, params=params,
                     headers={"X-Plex-Token": PLEX_TOKEN}, timeout=10)
    r.raise_for_status()
    return r


def _library_sections() -> list[tuple[str, Path]]:
    """(section key, folder) for every folder of every Plex library."""
    global _sections, _sections_at
    if time.time() - _sections_at > SECTIONS_TTL:
        root = ET.fromstring(_get("/library/sections").content)
        _sections = [(d.get("key"), Path(loc.get("path")))
                     for d in root.findall("Directory")
                     for loc in d.findall("Location")]
        _sections_at = time.time()
    return _sections


def _section_for(path: Path) -> tuple[str, Path] | None:
    for key, root in _library_sections():
        if path == root or root in path.parents:
            return key, root
    return None


def notify(*paths: str | Path) -> None:
    """Something changed at these paths: a film arrived, was renamed, moved
    away or deleted. Paths outside every Plex library are ignored, so this
    can be called for any change without first working out whether Plex
    cares."""
    if not PLEX_TOKEN:
        return
    global _timer
    with _lock:
        _pending.update(Path(p) for p in paths if p)
        if _timer is None:
            _timer = threading.Timer(SETTLE_SECONDS, _flush)
            _timer.daemon = True
            _timer.start()


def _flush() -> None:
    global _timer
    with _lock:
        paths, _timer = set(_pending), None
        _pending.clear()
    try:
        scans: set[tuple[str, Path]] = set()
        for p in paths:
            hit = _section_for(p)
            if not hit:
                continue
            key, root = hit
            # The film's own folder — the first level under the library root.
            # When that is gone (moved away, deleted) the whole library is
            # scanned instead: a partial scan of the root skips the same way
            # Plex's own one does, and never notices the film has gone.
            rel = p.relative_to(root).parts if p != root else ()
            folder = root / rel[0] if rel else root
            scans.add((key, folder if folder.exists() and folder != root else None))
        for key, folder in scans:
            if folder is None:
                _get(f"/library/sections/{key}/refresh")
            else:
                _get(f"/library/sections/{key}/refresh", path=str(folder))
            print(f"plex: asked section {key} to scan {folder or 'the whole library'}")
    except Exception as e:
        print(f"plex: could not ask for a scan ({e.__class__.__name__}: {e})")
