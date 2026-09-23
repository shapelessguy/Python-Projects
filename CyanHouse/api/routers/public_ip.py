"""Public address — keeps DuckDNS and Plex pointed at the home connection.

The work is a background loop (api/services/public_ip.py) started by
``init()``; the route only reports what it last saw, for checking on it.
"""
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.services import public_ip

router = APIRouter(prefix="/api/public-ip", tags=["public-ip"])


def init() -> None:
    public_ip.start()


@router.get("")
async def status(_user: str = Depends(require_user)):
    return public_ip.status()
