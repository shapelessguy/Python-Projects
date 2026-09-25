"""Resumable uploads — a plug-and-play router module.

Speaks tus 1.0.0 (tus.io), which is what `tus-js-client` in the SPA expects:
POST to create, HEAD to ask how much arrived, PATCH to append, DELETE to
abandon. See ``api/services/uploads.py`` for why the protocol is worth it
and where the bytes actually land.

Contract picked up by ``api/main.py`` auto-discovery: ``router`` and
``init()``. No ``versions()``: a finished upload bumps the prep counter
instead, which is what the Movies panel already watches.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from api.auth import require_user, require_media_area
from api.routers.prep import may_change
from api.services import uploads

router = APIRouter(prefix="/api/uploads", tags=["uploads"], dependencies=[Depends(require_media_area)])

PANEL = "movies"  # same permission as the panel that drives it

# Sent on every reply. A tus client refuses to talk to a server that does not
# announce the version it implements.
BASE = {"Tus-Resumable": uploads.TUS_VERSION, "Cache-Control": "no-store"}


def init() -> None:
    gone = uploads.sweep()
    if gone:
        print(f"uploads: cleared {gone} stale upload(s)")


def _wrap(exc: uploads.UploadError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


async def _may_write(user: str, upload_id: str) -> None:
    """Same rule as every other change to these folders (see may_change in
    routers/prep.py), applied to the folder this upload is going into."""
    try:
        area = await run_in_threadpool(uploads.area_of, upload_id)
    except uploads.UploadError as e:
        raise _wrap(e)
    may_change(user, area)


@router.options("")
async def options() -> Response:
    """What this server supports. tus-js-client does not need it, but a
    client that asks should not get a 405."""
    return Response(status_code=204, headers={
        **BASE,
        "Tus-Version": uploads.TUS_VERSION,
        "Tus-Extension": "creation,termination",
        "Tus-Max-Size": str(uploads.MAX_UPLOAD_BYTES),
    })


@router.post("")
async def create(request: Request, user: str = Depends(require_user)) -> Response:
    """Reserve an upload and answer with its URL.

    Destination comes from Upload-Metadata: `area` (the source key the panel
    uses), `folder` (a path inside it, "" for its root) and `relativePath`,
    which is the file's path *within a dropped folder* — that is what makes
    dropping a whole release folder land as that folder rather than as a pile
    of loose files."""
    try:
        meta = uploads.decode_metadata(request.headers.get("Upload-Metadata", ""))
        length = int(request.headers.get("Upload-Length", "-1"))
    except (uploads.UploadError, ValueError) as e:
        raise HTTPException(400, str(e))

    area = meta.get("area", "")
    may_change(user, area)
    name = meta.get("relativePath") or meta.get("filename") or ""
    try:
        state = await run_in_threadpool(
            uploads.create, area, meta.get("folder", ""), name, length)
    except uploads.UploadError as e:
        raise _wrap(e)
    except Exception as e:                      # a bad area, a vanished mount
        raise HTTPException(400, str(e))
    return Response(status_code=201, headers={
        **BASE,
        "Location": f"/api/uploads/{state['id']}",
        # The SPA reads this to show where the file will end up; tus itself
        # does not define it, and a client that ignores it loses nothing.
        "X-Upload-Target": state["rel_path"],
    })


@router.head("/{upload_id}")
async def head(upload_id: str, _user: str = Depends(require_user)) -> Response:
    """The resume point. Everything the client needs to carry on."""
    try:
        at, state = await run_in_threadpool(uploads.offset, upload_id)
    except uploads.UploadError as e:
        raise _wrap(e)
    return Response(status_code=200, headers={
        **BASE,
        "Upload-Offset": str(at),
        "Upload-Length": str(state["length"]),
    })


@router.patch("/{upload_id}")
async def patch(upload_id: str, request: Request,
                user: str = Depends(require_user)) -> Response:
    """Append a chunk at the offset the client says it is at.

    One chunk is read whole and written whole — bounded by MAX_CHUNK_BYTES,
    which is why that constant is small. Streaming it through would save the
    8 MB the SPA sends at a time and cost a thread hop per 64 KB; at these
    sizes the buffer is the cheaper end of that trade."""
    await _may_write(user, upload_id)
    if request.headers.get("Content-Type", "") != "application/offset+octet-stream":
        raise HTTPException(415, "PATCH body must be application/offset+octet-stream")
    try:
        at = int(request.headers.get("Upload-Offset", "-1"))
    except ValueError:
        raise HTTPException(400, "Upload-Offset must be a number")
    if at < 0:
        raise HTTPException(400, "Upload-Offset is required")
    if (request.headers.get("Content-Length") or "").isdigit():
        if int(request.headers["Content-Length"]) > uploads.MAX_CHUNK_BYTES:
            raise HTTPException(413, "that chunk is too large")

    body = await request.body()
    try:
        state = await run_in_threadpool(uploads.append, upload_id, at, (body,))
    except uploads.UploadError as e:
        if e.status_code == 409:
            # Tell it where we actually are, so the retry is right first time.
            try:
                current, _ = await run_in_threadpool(uploads.offset, upload_id)
                raise HTTPException(409, str(e), headers={**BASE, "Upload-Offset": str(current)})
            except uploads.UploadError:
                pass
        raise _wrap(e)
    return Response(status_code=204, headers={
        **BASE,
        "Upload-Offset": str(state.get("offset", 0)),
        **({"X-Upload-Done": "1"} if state.get("done") else {}),
    })


@router.delete("/{upload_id}")
async def delete(upload_id: str, user: str = Depends(require_user)) -> Response:
    """Abandon an upload and drop its partial."""
    await _may_write(user, upload_id)
    try:
        await run_in_threadpool(uploads.terminate, upload_id)
    except uploads.UploadError as e:
        raise _wrap(e)
    return Response(status_code=204, headers=BASE)
