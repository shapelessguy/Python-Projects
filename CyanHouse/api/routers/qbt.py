"""qBittorrent's Web UI, reverse-proxied under /api/qbt/ (api/services/webproxy.py).

Framed by the Media panel's Torrents tab. Going through the API rather than a
location of its own in nginx puts it behind the same login and "media"
visibility as the panel: anyone who can't open the Media panel can't reach
the torrent client either, from the LAN or the internet.

qBittorrent's own login still applies on top unless it is told to trust
localhost ("Bypass authentication for clients on localhost") — every request
it sees now comes from this process on 127.0.0.1.

The torrents are bound to the VPN interface (docker-compose.yml), and that
is not a setting the web UI gets to change: a save of the options goes
through without it, so the binding stays what the container started with.
"""
import json
from urllib.parse import parse_qs, urlencode

from fastapi import Depends, APIRouter

from api.config import QBT_URL
from api.services import webproxy
from api.auth import require_downloaders

router = APIRouter(prefix="/api/qbt", tags=["qbt"], include_in_schema=False, dependencies=[Depends(require_downloaders)])

PANEL = "media"  # the Media panel it lives in

# Which network interface, and which of its addresses, the torrents use.
_VPN_KEYS = ("current_network_interface", "current_interface_name", "current_interface_address")


def _keep_vpn(method: str, path: str, body: bytes) -> bytes:
    """A save of the options (a form with one field, `json`) loses the
    interface keys; one this can't read is refused rather than passed on."""
    if method != "POST" or path.rstrip("/").lower() != "api/v2/app/setpreferences":
        return body
    try:
        form = parse_qs(body.decode(), keep_blank_values=True, strict_parsing=True)
        prefs = json.loads(form["json"][0])
        if not isinstance(prefs, dict):
            raise ValueError
    except (ValueError, KeyError, IndexError, UnicodeDecodeError):
        raise ValueError("unreadable preferences")
    for key in _VPN_KEYS:
        prefs.pop(key, None)
    form["json"] = [json.dumps(prefs)]
    return urlencode(form, doseq=True).encode()


# own_parent: qBittorrent 5's page expects to be the top window (webproxy.py).
webproxy.mount(router, QBT_URL, strip_prefix=True, own_parent=True, rewrite=_keep_vpn)
