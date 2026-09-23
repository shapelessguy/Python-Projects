"""qBittorrent's Web UI, reverse-proxied under /api/qbt/ (api/services/webproxy.py).

Framed by the Media panel's Torrents tab. Going through the API rather than a
location of its own in nginx puts it behind the same login and "movies"
visibility as the panel: anyone who can't open the Media panel can't reach
the torrent client either, from the LAN or the internet.

qBittorrent's own login still applies on top unless it is told to trust
localhost ("Bypass authentication for clients on localhost") — every request
it sees now comes from this process on 127.0.0.1.
"""
from fastapi import APIRouter

from api.config import QBT_URL
from api.services import webproxy

router = APIRouter(prefix="/api/qbt", tags=["qbt"], include_in_schema=False)

PANEL = "movies"  # the Media panel it lives in

webproxy.mount(router, QBT_URL, strip_prefix=True)
