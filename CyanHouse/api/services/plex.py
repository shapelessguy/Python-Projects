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


# ── posters ──────────────────────────────────────────────────────────────
# The Movies panel's cover grid shows the posters Plex already has. Films are
# matched to Plex's entries by file path — the same path on both sides, since
# Plex reads the same library folders — never by title, so a film Plex has not
# matched (or not scanned yet) simply has no cover.
POSTERS_TTL = 120
# Plex being down is remembered for this long rather than asked again for
# every cover.
POSTERS_RETRY = 30
_posters_lock = threading.Lock()
_posters: dict[str, str] = {}
_posters_at = 0.0


def posters() -> dict[str, str]:
    """{file path: Plex thumb path} for every file in every movie library.
    Empty when there is no token or Plex cannot be reached."""
    global _posters, _posters_at
    if not PLEX_TOKEN:
        return {}
    with _posters_lock:
        if time.time() - _posters_at < POSTERS_TTL:
            return _posters
        try:
            root = ET.fromstring(_get("/library/sections").content)
            out: dict[str, str] = {}
            for d in root.findall("Directory"):
                if d.get("type") != "movie":
                    continue
                items = ET.fromstring(_get(f"/library/sections/{d.get('key')}/all", type=1).content)
                for v in items.findall("Video"):
                    thumb = v.get("thumb")
                    if not thumb:
                        continue
                    for part in v.iter("Part"):
                        if part.get("file"):
                            out[part.get("file")] = thumb
            _posters, _posters_at = out, time.time()
        except Exception as e:
            print(f"plex: could not read posters ({e.__class__.__name__}: {e})")
            _posters_at = time.time() - POSTERS_TTL + POSTERS_RETRY
        return _posters


def poster_image(thumb: str, width: int) -> tuple[bytes, str]:
    """The poster at `thumb`, scaled by Plex to `width` (2:3), as (bytes,
    content type)."""
    r = requests.get(PLEX_URL + "/photo/:/transcode",
                     params={"url": thumb, "width": width, "height": width * 3 // 2,
                             "minSize": 1, "upscale": 1},
                     headers={"X-Plex-Token": PLEX_TOKEN}, timeout=15)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "image/jpeg")


# ── public address ───────────────────────────────────────────────────────
# Plex learns its public address by asking plex.tv, and this machine's
# traffic leaves through NordVPN, so plex.tv answers with the VPN's address
# and the apps outside are sent there. api/services/public_ip.py gives Plex
# the real one instead, as a "custom server access URL" in the form Plex's
# own certificate covers: https://<a-b-c-d>.<cert id>.plex.direct:<port>.
_cert_id: str | None = None


def cert_id() -> str:
    """The id in Plex's certificate name (*.<id>.plex.direct), read from
    the certificate the local server presents."""
    global _cert_id
    if _cert_id is None:
        import re
        import socket
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        host = PLEX_URL.split("://", 1)[-1].split("/", 1)[0]
        name, _, port = host.partition(":")
        with socket.create_connection((name, int(port or 32400)), timeout=10) as raw, \
                ctx.wrap_socket(raw) as tls:
            der = tls.getpeercert(binary_form=True) or b""
        m = re.search(rb"\*\.([0-9a-f]{32})\.plex\.direct", der)
        if not m:
            raise RuntimeError("Plex's certificate is not a plex.direct one")
        _cert_id = m.group(1).decode()
    return _cert_id


def set_public_address(ip: str) -> str | None:
    """Point Plex's custom access URL at `ip`. Other custom URLs someone
    entered are kept; an older plex.direct one of this server's is replaced.
    Returns the URL when it changed something, None when it was already so."""
    if not PLEX_TOKEN:
        return None
    prefs = ET.fromstring(_get("/:/prefs").content)
    port = next((s.get("value") for s in prefs.iter("Setting")
                 if s.get("id") == "ManualPortMappingPort"), "") or "32400"
    current = next((s.get("value") for s in prefs.iter("Setting")
                    if s.get("id") == "customConnections"), "") or ""
    cid = cert_id()
    url = f"https://{ip.replace('.', '-')}.{cid}.plex.direct:{port}"
    kept = [u.strip() for u in current.split(",")
            if u.strip() and f".{cid}.plex.direct" not in u]
    wanted = ",".join([url, *kept])
    if wanted == current:
        return None
    r = requests.put(PLEX_URL + "/:/prefs", params={"customConnections": wanted},
                     headers={"X-Plex-Token": PLEX_TOKEN}, timeout=10)
    r.raise_for_status()
    return url
