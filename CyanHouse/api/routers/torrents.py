"""Torrents — read-only dashboard view of qBittorrent's Web API.

    GET /api/torrents  ->  api.services.qbittorrent.list_torrents()

Contract picked up by ``api/main.py`` auto-discovery: only ``router`` — no DB,
no ``init``/``versions`` needed (qBittorrent's session is lazily established
on first request, see api/services/qbittorrent.py).
"""
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from api.services import qbittorrent

router = APIRouter(prefix="/api/torrents", tags=["torrents"])


@router.get("")
async def list_torrents():
    try:
        return await run_in_threadpool(qbittorrent.list_torrents)
    except qbittorrent.TorrentsError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
