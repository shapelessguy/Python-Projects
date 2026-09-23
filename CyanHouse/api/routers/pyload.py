"""pyLoad-ng's Web UI, reverse-proxied under /api/pyload/ (api/services/webproxy.py).

Framed by the Media panel's Downloads tab, behind the same login and "movies"
visibility as the panel. pyLoad runs in docker-compose.yml's `pyload`
service, published on the loopback only, and is configured (webui.prefix in
docker/pyload/config/settings/pyload.cfg) to serve its pages under this same
path — its links are absolute, so they have to already carry the prefix.
Its own login is skipped (webui.autologin): the CyanHouse one is the lock.
"""
from fastapi import APIRouter

from api.config import PYLOAD_URL
from api.services import webproxy

router = APIRouter(prefix="/api/pyload", tags=["pyload"], include_in_schema=False)

PANEL = "movies"  # the Media panel it lives in

webproxy.mount(router, PYLOAD_URL, strip_prefix=False)
