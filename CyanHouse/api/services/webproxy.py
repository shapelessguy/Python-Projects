"""Pass-through reverse proxy for third-party web UIs framed in the SPA.

Each one is mounted under /api/<name>/ by its own router module, which is
what puts it behind the CyanHouse login (the router's PANEL) and makes it
same-origin with the SPA — both qBittorrent and pyLoad refuse to be framed
from anywhere else. See api/routers/qbt.py and api/routers/pyload.py.
"""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

# Per-hop, or describing a body/connection this side re-frames itself.
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailer", "transfer-encoding", "upgrade", "content-length"}
# Dropped on the way in. Host must name the upstream, not us. Origin/Referer:
# these apps' CSRF checks reject any whose host differs from the Host they
# get — which through a proxy they always do. The CyanHouse login the router
# already demands (a SameSite=Strict cookie) is the CSRF guard now.
# Authorization would be our own Basic credential, meaningless to them.
_DROP_IN = _HOP | {"host", "origin", "referer", "authorization"}


# Put at the top of a framed app's main page when it takes itself to be the
# top window. qBittorrent 5's pages reach their own main page as
# `window.parent` — its dialogs are frames inside it, and for the main page
# itself parent is itself only when it is not framed. Framed in the panel,
# parent is the SPA, and the page fails before drawing anything. `parent` is
# one of the window properties a page may replace, so the main page points
# it back at itself; its dialogs, framed inside it, keep theirs.
_OWN_PARENT = b"<script>window.parent = window;</script>"


def mount(router: APIRouter, upstream: str, *, strip_prefix: bool, own_parent: bool = False) -> None:
    """Add the proxy routes to `router` (whose prefix is the public path).

    strip_prefix: the upstream serves from its own root (qBittorrent), so the
    public prefix is removed on the way in; otherwise the upstream has been
    configured to live under the same prefix itself (pyLoad's webui.prefix)
    and paths go through unchanged.
    own_parent: the app's main page (its root) gets _OWN_PARENT first thing
    in its <head>. Everything else still passes through untouched."""
    prefix = router.prefix
    upstream = upstream.rstrip("/")
    client = httpx.AsyncClient(base_url=upstream, timeout=httpx.Timeout(30.0, read=300.0))

    @router.get("", include_in_schema=False)
    def _slash():
        # Their pages link relative to a directory.
        return RedirectResponse(prefix + "/")

    @router.api_route("/{path:path}", include_in_schema=False,
                      methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def _proxy(path: str, request: Request):
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_IN}
        target = "/" + path if strip_prefix else f"{prefix}/{path}"
        req = client.build_request(
            request.method, target, params=request.query_params, headers=headers,
            # Buffered, not streamed: qBittorrent's HTTP server doesn't take a
            # chunked request body, and without a length a stream would be
            # sent as one. The bodies are forms and .torrent files — small.
            content=await request.body())
        try:
            resp = await client.send(req, stream=True)
        except httpx.HTTPError as e:
            return PlainTextResponse(f"unreachable at {upstream}: {e!r}", status_code=502)
        out = []
        for k, v in resp.headers.multi_items():  # keeps repeated Set-Cookie apart
            if k.lower() in _HOP:
                continue
            if k.lower() == "location":
                # An absolute redirect names the upstream's own address, which
                # the browser can't reach; make it path-only, and put the
                # prefix back if the upstream never knew about it.
                if v.startswith(upstream):
                    v = v[len(upstream):] or "/"
                if strip_prefix and v.startswith("/"):
                    v = prefix + v
            out.append((k.encode("latin-1"), v.encode("latin-1")))
        if (own_parent and request.method == "GET" and path in ("", "index.html")
                and resp.headers.get("content-type", "").startswith("text/html")):
            body = await resp.aread()   # decoded, if it came compressed
            await resp.aclose()
            head = body.lower().find(b"<head>")
            at = head + len(b"<head>") if head >= 0 else 0
            body = body[:at] + _OWN_PARENT + body[at:]
            out = [(k, v) for k, v in out if k.lower() != b"content-encoding"]
            response = Response(body, status_code=resp.status_code)
            response.raw_headers = out + [(b"content-length", str(len(body)).encode())]
            return response
        response = StreamingResponse(resp.aiter_raw(), status_code=resp.status_code,
                                     background=BackgroundTask(resp.aclose))
        response.raw_headers = out
        return response
