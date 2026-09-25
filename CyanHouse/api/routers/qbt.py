"""qBittorrent's Web UI, reverse-proxied under /api/qbt/ (api/services/webproxy.py).

Framed by the Media panel's Torrents tab. Going through the API rather than a
location of its own in nginx puts it behind the same login and "movies"
visibility as the panel: anyone who can't open the Media panel can't reach
the torrent client either, from the LAN or the internet.

qBittorrent's own login still applies on top unless it is told to trust
localhost ("Bypass authentication for clients on localhost") — every request
it sees now comes from this process on 127.0.0.1.
"""
from fastapi import Depends, APIRouter

from api.config import QBT_URL
from api.services import webproxy
from api.auth import require_downloaders

router = APIRouter(prefix="/api/qbt", tags=["qbt"], include_in_schema=False, dependencies=[Depends(require_downloaders)])

PANEL = "movies"  # the Media panel it lives in

# own_parent: qBittorrent 5's page expects to be the top window (webproxy.py).
webproxy.mount(router, QBT_URL, strip_prefix=True, own_parent=True)
