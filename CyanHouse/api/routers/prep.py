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

from api.auth import has_permission, require_permission, require_user
from api.services import movie_prep, movies, remux_queue, tmdb

router = APIRouter(prefix="/api/prep", tags=["prep"])

VERSION_NAMES = ["prep"]
PANEL = "movies"  # same permission as the Movies panel it lives in


def init() -> None:
    movie_prep.init()
    remux_queue.init()
    # Keeps the pictures' sizes in step with the Images folder, for the
    # gallery (api/services/image_dims.py).
    from api.services import image_dims
    image_dims.start()


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


@router.post("/execute", status_code=202)
async def execute(
    area: str = Query(...),
    plan: dict = Body(...),
    user: str = Depends(require_user),
):
    """Queue one film for remuxing, and save the plan it was queued with.

    Always accepted when the film *can* be remuxed — the queue runs them in
    order — and refused at once when it cannot (not identified, a name
    already taken), so the answer is never a job that fails a second later.

    Allowed wherever moving is: it takes a film out of an inbox and puts the
    result in that inbox's own output, which is a move within its workspace."""
    may_move(user, area, movie_prep.output_of(area))
    try:
        return await run_in_threadpool(remux_queue.enqueue, area, plan, user)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/remux_all", status_code=202)
async def remux_all(area: str = Query(...), user: str = Depends(require_user)):
    """Queue every film in an inbox that is ready, and say why each of the
    rest is not."""
    may_move(user, area, movie_prep.output_of(area))
    try:
        return await run_in_threadpool(remux_queue.enqueue_all, area, user)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.get("/jobs")
async def remux_jobs(_user: str = Depends(require_user)):
    """The queue: what is running, what is waiting, and what has finished."""
    return {"jobs": remux_queue.jobs()}


@router.delete("/jobs/{job_id}")
async def remove_job(job_id: str, user: str = Depends(require_user)):
    """Drop a queued remux, stop a running one, or clear a finished one.
    Whoever may queue in that area may take out of it."""
    try:
        where = remux_queue.job_area(job_id)
        may_move(user, where, movie_prep.output_of(where))
        return await run_in_threadpool(remux_queue.remove, job_id)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/jobs/clear")
async def clear_jobs(_user: str = Depends(require_user)):
    """Forget every finished remux. The queue itself is untouched."""
    await run_in_threadpool(remux_queue.clear_finished)
    return {"jobs": remux_queue.jobs()}


@router.put("/plan")
async def save_plan(
    area: str = Query(...),
    plan: dict = Body(...),
    user: str = Depends(require_user),
):
    """Remember what was decided about a film — its name, and which tracks it
    keeps, in which language, at what delay. Sent on every change, so the
    decisions outlive the tab they were made in, and a queued remux uses the
    latest of them when its turn comes."""
    may_change(user, area)
    try:
        return await run_in_threadpool(movie_prep.save_plan, area, plan)
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
        inbox, library = movie_prep.area(area)
        return await run_in_threadpool(movie_prep.execute, plan, library, True, inbox)
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
    """The bytes, for things a browser can render itself: images, and audio
    (which seeks through Range requests — FileResponse answers those)."""
    try:
        resolved = await run_in_threadpool(movie_prep.resolve_in_area, area, path)
    except movie_prep.PrepError as e:
        raise _wrap(e)
    if movie_prep.file_kind(resolved) not in ("image", "audio"):
        raise HTTPException(415, "only images and audio are served raw")
    return FileResponse(resolved, headers={"Cache-Control": "no-store"})


@router.get("/thumb")
async def thumb(area: str = Query(...), path: str = Query(...), w: int = Query(400, ge=32, le=2000),
                _user: str = Depends(require_user)):
    """A small JPEG of a picture, for galleries (api/services/thumbs.py)."""
    from api.services import thumbs
    try:
        out = await run_in_threadpool(thumbs.thumbnail, area, path, w)
    except movie_prep.PrepError as e:
        raise _wrap(e)
    # The page puts the picture's time in the URL (`v`), so a browser may
    # keep this: a changed picture is asked for under a new URL.
    return FileResponse(out, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/space")
async def disk_space(area: str = Query(...), _user: str = Depends(require_user)):
    """The disk this folder lives on: what it is called, and how full."""
    try:
        return await run_in_threadpool(movie_prep.disk_usage, area)
    except movie_prep.PrepError as e:
        raise _wrap(e)


# Who may change what.
#
# A staging area with an inbox is a workspace: its two folders — the work
# waiting and the work done — are open to anyone who can see them. Rename,
# delete, upload, reorganise, remux, and move freely *between those two*.
# What needs the publish permission is everything past that: sending work to
# another area, and any change to a folder that is not part of a workspace
# (the film library, the series library, any output-only entry). That is the
# shelf, not the workbench.
#
# Looking is always open: browsing, reading, playing.
def _publisher(user: str) -> bool:
    return has_permission(user, "publish")


def may_change(user: str, area: str) -> None:
    """Rename, delete, upload, move within — anything that stays in `area`."""
    if _publisher(user) or movie_prep.workspace_of(area):
        return
    raise HTTPException(403, "outside a staging workspace, changes need the publish permission")


def may_move(user: str, from_area: str, to_area: str) -> None:
    """A move changes both ends, so both are judged: without the publish
    permission, both have to be halves of the same workspace."""
    if _publisher(user):
        return
    here = movie_prep.workspace_of(from_area)
    if not here:
        raise HTTPException(403, "outside a staging workspace, changes need the publish permission")
    if movie_prep.workspace_of(to_area) != here:
        raise HTTPException(
            403, "without the publish permission, things move only within their own workspace")


@router.post("/rename")
async def rename_entry(
    area: str = Query(...),
    path: str = Query(...),
    name: str = Query(..., min_length=1, max_length=255),
    user: str = Depends(require_user),
):
    """Rename one file or folder where it sits."""
    may_change(user, area)
    try:
        return await run_in_threadpool(movie_prep.rename_entry, area, path, name)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/mkdir")
async def make_folder(
    area: str = Query(...),
    path: str = Query("", description="the folder to create it in; '' is the root"),
    name: str = Query(..., min_length=1, max_length=255),
    user: str = Depends(require_user),
):
    """Create an empty folder."""
    may_change(user, area)
    try:
        return await run_in_threadpool(movie_prep.make_folder, area, path, name)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/movepath")
async def move_entry(
    area: str = Query(..., description="the area the thing is in now"),
    path: str = Query(..., description="what to move, relative to that area"),
    to_area: str = Query(..., description="the area to move it into"),
    to: str = Query("", description="destination folder in that area; '' is its root"),
    user: str = Depends(require_user),
):
    """Move a file or folder into another folder — the drag-and-drop in the
    tree. Both ends are checked: taking something out of a folder is as much
    a change to it as putting something in."""
    may_move(user, area, to_area)
    try:
        return await run_in_threadpool(movie_prep.move_entry, area, path, to_area, to)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/resolve")
async def resolve_conflict(
    area: str = Query(..., description="where the file is now"),
    path: str = Query(...),
    to_area: str = Query(...),
    dest: str = Query(..., description="the path it clashed with, in to_area"),
    action: str = Query(..., pattern="^(replace|keep)$"),
    upto: str = Query("", description="the folder that was being moved"),
    user: str = Depends(require_user),
):
    """Settle a file a move left behind because the destination had one of
    the same name: replace that one, or keep both."""
    may_move(user, area, to_area)
    try:
        return await run_in_threadpool(
            movie_prep.resolve_conflict, area, path, to_area, dest, action, upto)
    except movie_prep.PrepError as e:
        raise _wrap(e)


@router.post("/delete")
async def delete_entry(
    area: str = Query(...),
    path: str = Query(...),
    user: str = Depends(require_user),
):
    """Delete a file, or a folder and everything under it. For good — the
    panel asks twice before it calls this."""
    may_change(user, area)
    try:
        return await run_in_threadpool(movie_prep.delete_entry, area, path)
    except movie_prep.PrepError as e:
        raise _wrap(e)


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
