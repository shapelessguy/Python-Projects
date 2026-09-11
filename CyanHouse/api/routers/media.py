"""Media playback — a plug-and-play router module (see food.py). Thin HTTP
wrapper around api/services/media.py; no state, no version counter, so this
module exposes only `router`.

    GET /api/media/info?path=       -> {duration}
    GET /api/media/stream?path=&start=0.0  -> fragmented-mp4 stream
    GET /api/media/subtitles?path=  -> text/vtt
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from api.services import media

router = APIRouter(prefix="/api/media", tags=["media"])


def _require_file(path: str) -> None:
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"no such file: {path}")


@router.get("/info")
async def info(path: str):
    _require_file(path)
    try:
        duration = await run_in_threadpool(media.probe_duration, path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ffprobe failed: {e}")
    return {"duration": duration}


@router.get("/stream")
def stream(path: str, start: float = 0.0):
    _require_file(path)
    return StreamingResponse(media.stream_from(path, start), media_type="video/mp4")


@router.get("/subtitles")
async def subtitles(path: str):
    _require_file(path)
    try:
        vtt = await run_in_threadpool(media.to_vtt, path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"subtitle read failed: {e}")
    return Response(vtt, media_type="text/vtt")
