"""Movies service — a plug-and-play router module.

Browse ``MOVIES_DIR`` and stream any file in it, transcoded on demand with
subtitles burned in — see ``api/services/movies.py`` for why it's built that
way and what the seek-by-restart contract is.

Contract picked up by ``api/main.py`` auto-discovery: ``router`` and
``init()``. There's no database and nothing mutable, so no ``versions()``:
the library is the filesystem, and the panel refetches it on demand rather
than off the version poll.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from api.auth import require_user
from api.services import movies

router = APIRouter(prefix="/api/movies", tags=["movies"])

PANEL = "movies"  # gates the whole router behind permissions.visibility -- see api/auth.py


def init() -> None:
    movies.init()


def _wrap(exc: movies.MovieError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


@router.get("/list")
async def list_movies(refresh: bool = False, _user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(movies.list_movies, refresh)
    except movies.MovieError as e:
        raise _wrap(e)


@router.get("/info")
async def movie_info(id: str = Query(...), _user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(movies.info, id)
    except movies.MovieError as e:
        raise _wrap(e)


@router.get("/stream")
async def stream(
    id: str = Query(...),
    sid: str = Query(..., min_length=1, max_length=64),
    t: float = Query(0.0, ge=0),
    a: int | None = Query(None, ge=0),
    s: int | None = Query(None, ge=0),
    h: int = Query(movies.DEFAULT_HEIGHT, ge=0, le=2160),  # 0 = "Original" (stream copy)
    _user: str = Depends(require_user),
):
    """The stream itself: fragmented MP4, no byte ranges, starting at ``t``.

    Spawning ffmpeg touches the network mount and can block for a moment, so
    it happens in the threadpool; the generator it returns is a *sync* one,
    which Starlette also iterates off the event loop. ``Accept-Ranges: none``
    tells the browser not to try seeking this — seeking is a new request with
    a new ``t``, and the player adds that offset back on itself."""
    try:
        # Split in two on purpose: `prepare` blocks (ffprobe, and a first-time
        # subtitle extraction can take minutes on a large file) so it goes to
        # the threadpool, while `open_stream` must stay on the event loop —
        # its async generator is what makes a dropped connection kill the
        # transcode instead of orphaning it.
        cmd = await run_in_threadpool(movies.prepare, id, sid, t, a, s, h)
        chunks = await movies.open_stream(sid, cmd)
    except movies.MovieError as e:
        raise _wrap(e)
    return StreamingResponse(
        chunks,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "none",
            "Cache-Control": "no-store",
            "X-Stream-Offset": f"{t:.3f}",
        },
    )


@router.post("/stop")
async def stop(sid: str = Query(..., min_length=1, max_length=64),
               _user: str = Depends(require_user)):
    """Explicit teardown for the case the browser's own disconnect is slow to
    arrive (pausing, or closing the tab mid-fragment) — idempotent."""
    await run_in_threadpool(movies.stop, sid)
    return {"stopped": sid}
