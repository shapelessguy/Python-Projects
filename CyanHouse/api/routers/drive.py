"""Media drive — Plex, qBittorrent and pyLoad run only while it's there.

The work is a background loop (api/services/drive_watch.py) started by
``init()``; the route only reports what it last saw, for checking on it.
"""
from fastapi import APIRouter, Depends

from api.auth import require_user
from api.services import drive_watch

router = APIRouter(prefix="/api/drive", tags=["drive"])


def init() -> None:
    drive_watch.start()


@router.get("")
async def status(_user: str = Depends(require_user)):
    return drive_watch.status()
