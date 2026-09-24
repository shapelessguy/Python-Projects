"""Music staging — recognise songs in a music inbox and file them into its
output as Album Artist/Album/NN - Title. See api/services/music_prep.py.

Browsing, moving, uploading and deleting in a music pair are the prep
router's, exactly as for films; only this part is music's own.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from api.auth import require_user
from api.routers.prep import may_change
from api.services import music_library, music_prep
from api.services.movie_prep import PrepError

router = APIRouter(prefix="/api/music", tags=["music"])

PANEL = "movies"  # the Media panel it lives in


def init() -> None:
    music_prep.start_auto()


def _wrap(e: PrepError) -> HTTPException:
    return HTTPException(e.status_code, str(e))


@router.get("/identify")
async def identify(
    area: str = Query(...),
    path: str = Query(...),
    artist: str | None = Query(None, max_length=300),
    title: str | None = Query(None, max_length=300),
    _user: str = Depends(require_user),
):
    """What a song in the inbox is, and every album it could be filed
    under, best first. `artist`/`title` search again with those instead of
    what the file says."""
    try:
        return await run_in_threadpool(music_prep.identify, area, path, artist, title)
    except PrepError as e:
        raise _wrap(e)
    except Exception as e:
        raise HTTPException(502, f"MusicBrainz lookup failed: {e}")


@router.get("/auto")
async def auto_status(area: str = Query(...), _user: str = Depends(require_user)):
    """What the background filing is doing in this inbox, and which songs it
    left for a person to look at, with why."""
    return await run_in_threadpool(music_prep.auto_status, area)


@router.post("/file")
async def file_song(
    area: str = Query(...),
    path: str = Query(...),
    choice: dict = Body(..., description="one of /identify's options, possibly edited"),
    user: str = Depends(require_user),
):
    """Tag the song with the chosen album and move it into the output."""
    may_change(user, area)
    try:
        return await run_in_threadpool(music_prep.file_song, area, path, choice)
    except PrepError as e:
        raise _wrap(e)


@router.get("/cover")
async def album_cover(rg: str = Query(...), _user: str = Depends(require_user)):
    """An album's front cover (Cover Art Archive), for the options list."""
    try:
        data = await run_in_threadpool(music_prep.cover, rg)
    except PrepError as e:
        raise _wrap(e)
    except Exception as e:
        raise HTTPException(502, f"could not get the cover: {e}")
    if not data:
        raise HTTPException(404, "no cover")
    return Response(data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=604800"})


@router.get("/library")
async def music_library_listing(_user: str = Depends(require_user)):
    """The music library as songs, albums and artists, from the files' tags."""
    try:
        return await run_in_threadpool(music_library.library)
    except PrepError as e:
        raise _wrap(e)


@router.get("/art")
async def album_art(folder: str = Query(...), _user: str = Depends(require_user)):
    """An album folder's cover.jpg."""
    try:
        path = await run_in_threadpool(music_library.cover, folder)
    except PrepError as e:
        raise _wrap(e)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
