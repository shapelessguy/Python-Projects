"""Movie preparation — a plug-and-play router module.

Turns a "dirty" download in a staging folder into one clean MKV: correct
name from TMDb, every audio and subtitle track tagged and named with its
language code, per-track sync fixed, external subtitles folded in, junk
removed. See ``api/services/movie_prep.py`` for why it is built this way.

The films here are streamable through the existing /api/movies/stream (their
ids carry an ``@area/`` prefix), which is the point: you check a subtitle's
timing in the player, with the delay applied live, and only then commit a
remux you already know is right.

Contract picked up by ``api/main.py`` auto-discovery: ``router``, ``init()``
(starts the folder watcher) and ``versions()`` — the staging folders are
watched every few seconds and the counter bumps when their contents change,
so the SPA's existing once-a-second /api/version poll is enough to keep the
list honest without re-probing anything.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from api.auth import require_permission, require_user
from api.services import movie_prep, movies, tmdb

router = APIRouter(prefix="/api/prep", tags=["prep"])

VERSION_NAMES = ["prep"]
PANEL = "movies"  # same permission as the Movies panel it lives in


def init() -> None:
    movie_prep.init()


def versions(user: str | None) -> dict[str, int]:
    return {"prep": movie_prep.version()}


def _wrap(exc) -> HTTPException:
    return HTTPException(getattr(exc, "status_code", 400), str(exc))


@router.get("/areas")
async def list_areas(_user: str = Depends(require_user)):
    """The staging folders from secrets.json, each flagged ready or not so
    the UI can say *why* an area is empty rather than just showing nothing."""
    return {"areas": list((await run_in_threadpool(movie_prep.areas)).values()),
            "sources": await run_in_threadpool(movie_prep.sources),
            "tmdb": tmdb.configured(),
            # Sent with the areas so the track editor can offer a picker
            # rather than a free-text box -- a typo there is a track the
            # muxer refuses, discovered only at the end of a mux.
            "languages": movie_prep.language_options(),
            }


@router.get("/scan")
async def scan_area(area: str = Query(...), _user: str = Depends(require_user)):
    try:
        return {"area": area, "films": await run_in_threadpool(movie_prep.scan_area, area)}
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.get("/identify")
async def identify(
    title: str = Query(..., min_length=1),
    year: str = Query(""),
    _user: str = Depends(require_user),
):
    """Ask TMDb what this film is. Deliberately separate from /scan: the scan
    is offline and fast, the lookup is a network call the user triggers."""
    try:
        return await run_in_threadpool(tmdb.identify, title, year)
    except tmdb.TmdbError as e:
        raise _wrap(e)


@router.post("/execute")
async def execute(
    area: str = Query(...),
    plan: dict = Body(...),
    _user: str = Depends(require_user),
):
    """Mux, verify, then move the leftovers to the area's trash — in that
    order. Nothing is deleted outright, so a bad run is recoverable."""
    try:
        _, library = movie_prep.area(area)
        return await run_in_threadpool(movie_prep.execute, plan, library)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/preview")
async def preview(
    area: str = Query(...),
    plan: dict = Body(...),
    _user: str = Depends(require_user),
):
    """The exact command that would run, and anything still blocking it.
    Cheap, and it makes the mux inspectable before it touches a file."""
    try:
        _, library = movie_prep.area(area)
        return await run_in_threadpool(movie_prep.execute, plan, library, True)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.get("/files")
async def list_files(area: str = Query(...), _user: str = Depends(require_user)):
    """Everything in the staging folder, not just the films — the subtitles,
    the release notes and the junk all have to be visible to be judged."""
    try:
        return {"area": area, "files": await run_in_threadpool(movie_prep.browse, area)}
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.get("/text")
async def read_text(area: str = Query(...), path: str = Query(...),
                    _user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(movie_prep.read_text, area, path)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.get("/info")
async def file_info(area: str = Query(...), path: str = Query(...),
                    _user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(movie_prep.describe, area, path)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.get("/raw")
async def raw_file(area: str = Query(...), path: str = Query(...),
                   _user: str = Depends(require_user)):
    """The bytes, for things a browser can render itself — images, mainly."""
    try:
        resolved = await run_in_threadpool(movie_prep.resolve_in_area, area, path)
    except movie_prep.PrepError as e:
        raise _wrap(e)
    if movie_prep.file_kind(resolved) != "image":
        raise HTTPException(415, "only images are served raw")
    return FileResponse(resolved, headers={"Cache-Control": "no-store"})


@router.get("/progress")
async def mux_progress(area: str = Query(...), target: str = Query(...),
                       _user: str = Depends(require_user)):
    """How far along a mux is. Polled while /execute is in flight — that call
    blocks until the file is written and verified, so the percentage has to
    come from somewhere else."""
    return movie_prep.progress(f"{area}:{target}")


@router.post("/move")
async def move_film(
    id: str = Query(...),
    to: str = Query(..., description="destination source key: '' for the library"),
    _user: str = Depends(require_permission("publish")),
):
    """Move a film's folder to another configured folder.

    Gated on its own permission: every other action here stays inside a
    staging folder, and this one can put a file into the real library."""
    try:
        return await run_in_threadpool(movie_prep.move_film, id, to)
    except (movie_prep.PrepError, movies.MovieError) as e:
        raise _wrap(e)
