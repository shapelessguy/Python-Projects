"""Movies service — a plug-and-play router module.

Browse ``MOVIES_DIR`` and stream any file in it, transcoded on demand with
subtitles burned in — see ``api/services/movies.py`` for why it's built that
way and what the seek-by-restart contract is.

Contract picked up by ``api/main.py`` auto-discovery: ``router`` and
``init()``. There's no database and nothing mutable, so no ``versions()``:
the library is the filesystem, and the panel refetches it on demand rather
than off the version poll.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from api.auth import require_user
from api.services import movie_prep, movie_subs, movies

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


@router.post("/subtitles")
async def upload_subtitle(
    id: str = Query(...),
    files: list[UploadFile] = File(...),
    _user: str = Depends(require_user),
):
    """Attach one or more subtitle files to a film.

    A list rather than a single file because VobSub is two files — `.idx` and
    `.sub` — that only mean anything together. Text formats, `.sup` and a
    VobSub pair can all arrive in the same request.

    Partial success is the normal answer, not an error: drop eight subtitles
    in and the two that are really a .nfo and a screenshot are named and
    skipped while the other six are stored. So the reply is always the
    refreshed track list plus what was taken and what was not — a whole
    batch is only refused when the *film* cannot be resolved.

    Everything is stored under MOVIES_DATA_DIR and linked by the film's
    fingerprint, never written into the library — the movie folders stay
    exactly as they are."""
    payload = [(f.filename or "", await f.read()) for f in files]
    try:
        return await run_in_threadpool(_store_subtitle, id, payload)
    except movie_subs.SubtitleError as e:
        raise HTTPException(e.status_code, str(e))
    except movies.MovieError as e:
        raise _wrap(e)


def _store_subtitle(movie_id: str, payload: list[tuple[str, bytes]]) -> dict:
    path = movies.resolve(movie_id)
    meta = movies.info(movie_id)
    try:
        where = str(path.relative_to(movies.MOVIES_DIR))
    except ValueError:
        # Not in the film library: a staging folder, or the series library.
        # Only a human-readable hint in the index — the fingerprint is what
        # actually links the subtitle to the film — so the absolute path is
        # a fine answer, and raising here turned an upload onto a staged
        # film into a 500.
        where = str(path)
    result = movie_subs.add(
        movies.fingerprint(path), meta["title"], where, payload,
    )
    if result["accepted"]:
        # The probe is cached per (path, mtime, size) and the film itself hasn't
        # changed, so the new track would not otherwise show up.
        movies.forget(movie_id)
        meta = movies.info(movie_id)
        # A film in a staging inbox has the upload as a track of its remux
        # plan now; this is what makes the panel fetch the plan again.
        movie_prep._bump()
    return {"info": meta, **result}


@router.delete("/subtitles")
async def delete_subtitle(
    id: str = Query(...),
    sub: str = Query(..., min_length=1, max_length=64),
    _user: str = Depends(require_user),
):
    """Remove an uploaded subtitle. Only ever touches this service's own
    store — a subtitle found in the movie folder isn't ours to delete."""
    try:
        return await run_in_threadpool(_drop_subtitle, id, sub)
    except movie_subs.SubtitleError as e:
        raise HTTPException(e.status_code, str(e))
    except movies.MovieError as e:
        raise _wrap(e)


def _drop_subtitle(movie_id: str, upload_id: str) -> dict:
    path = movies.resolve(movie_id)
    movie_subs.remove(movies.fingerprint(path), upload_id)
    movies.forget(movie_id)
    movie_prep._bump()
    return movies.info(movie_id)


@router.get("/stream")
async def stream(
    id: str = Query(...),
    sid: str = Query(..., min_length=1, max_length=64),
    t: float = Query(0.0, ge=0),
    a: int | None = Query(None, ge=0),
    s: int | None = Query(None, ge=0),
    h: int = Query(movies.DEFAULT_HEIGHT, ge=0, le=2160),  # 0 = "Original" (stream copy)
    # Milliseconds, signed. Positive pushes the track later, negative earlier
    # -- the same sense a desktop player's subtitle-delay control uses. Capped
    # at +/-10 minutes, which is far past any real desync and keeps a typo
    # from seeking ffmpeg somewhere absurd.
    sd: int = Query(0, ge=-600000, le=600000),
    ad: int = Query(0, ge=-600000, le=600000),
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
        cmd = await run_in_threadpool(
            movies.prepare, id, sid, t, a, s, h, sd / 1000.0, ad / 1000.0)
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
            "X-Sub-Delay-Ms": str(sd),
            "X-Audio-Delay-Ms": str(ad),
        },
    )


@router.post("/stop")
async def stop(sid: str = Query(..., min_length=1, max_length=64),
               _user: str = Depends(require_user)):
    """Explicit teardown for the case the browser's own disconnect is slow to
    arrive (pausing, or closing the tab mid-fragment) — idempotent."""
    await run_in_threadpool(movies.stop, sid)
    return {"stopped": sid}
