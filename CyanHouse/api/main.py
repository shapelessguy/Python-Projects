"""FastAPI entry point.

    uvicorn api.main:app --reload   (from the project root)

Serves the REST API under /api and, if react_ui/dist exists, the built SPA at /.
Every /api response carries X-<Service>-Version headers; clients also poll
GET /api/version once a second to know when to refetch.

Router modules under ``api/routers/`` are auto-discovered — a new service is
just a file there exposing ``router`` (and optionally ``init`` / ``versions``),
with no edit to this file. See ``routers/food.py`` for the template.
"""
import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api import routers as _routers_pkg
from api.auth import require_panel, require_user, visible_panels
from api.config import DEV_ORIGINS, FRONTEND_DIST
from api.db import connect, diary_version_key, get_version, init_db


def _discover_router_modules() -> list:
    """Every importable module in api.routers that exposes a `router`."""
    mods = []
    for info in pkgutil.iter_modules(_routers_pkg.__path__):
        mod = importlib.import_module(f"{_routers_pkg.__name__}.{info.name}")
        if hasattr(mod, "router"):
            mods.append(mod)
    return mods


ROUTER_MODULES = _discover_router_modules()


def _collect_versions(user: str | None) -> dict[str, int]:
    """The diary counter is per-user (`"<user>:diary_version"`), weather is
    global; pluggable service modules report their own per-user counters via a
    module-level ``versions(user)`` function. Tolerant of a not-yet-initialised
    DB / missing user so it is safe before lifespan runs and on 401s."""
    out: dict[str, int] = {"diary": 0, "weather": 0}
    try:
        with connect() as conn:
            if user:
                out["diary"] = get_version(conn, diary_version_key(user))
            out["weather"] = get_version(conn, "weather_version")
    except Exception:
        pass
    for mod in ROUTER_MODULES:
        fn = getattr(mod, "versions", None)
        if callable(fn):
            try:
                out.update(fn(user))
            except Exception:
                for n in getattr(mod, "VERSION_NAMES", []):
                    out.setdefault(n, 0)
    return out


# Header names are static (don't touch the DB at import time).
_VERSION_NAMES = ["diary", "weather"]
for _m in ROUTER_MODULES:
    for _n in getattr(_m, "VERSION_NAMES", []):
        if _n not in _VERSION_NAMES:
            _VERSION_NAMES.append(_n)
EXPOSED_VERSION_HEADERS = [f"X-{name.capitalize()}-Version" for name in _VERSION_NAMES]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    for mod in ROUTER_MODULES:
        init = getattr(mod, "init", None)
        if callable(init):
            init()
    yield


app = FastAPI(title="Cyan House API", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)

# Neither Swagger UI nor ReDoc ship a dark theme, and there's no supported
# hook to just add CSS on top of the default page — get_swagger_ui_html /
# get_redoc_html only let you swap the *whole* stylesheet, not extend it. So:
# default docs disabled above, replaced with these two routes that grab the
# normal generated HTML and splice one extra <style> tag into <head>. The
# actual dark effect is a CSS filter inverting the whole page then
# hue-rotating it back to sane colors (a standard trick for "dark-mode-ify an
# app you don't control the stylesheet of") — images/logos get re-inverted so
# they don't come out looking like photo negatives.
_DARK_MODE_CSS = """
<style>
  html { background: #1a1a1a; }
  body { filter: invert(92%) hue-rotate(180deg); background: #fff; }
  img, svg, .swagger-ui .topbar { filter: invert(100%) hue-rotate(180deg); }
</style>
"""


def _inject_dark_css(html: HTMLResponse) -> HTMLResponse:
    body = html.body.decode() if isinstance(html.body, bytes) else html.body
    return HTMLResponse(body.replace("</head>", _DARK_MODE_CSS + "</head>"))


@app.get("/docs", include_in_schema=False)
async def swagger_docs():
    return _inject_dark_css(get_swagger_ui_html(openapi_url=app.openapi_url, title=f"{app.title} - Docs"))


@app.get("/redoc", include_in_schema=False)
async def redoc_docs():
    return _inject_dark_css(get_redoc_html(openapi_url=app.openapi_url, title=f"{app.title} - ReDoc"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,  # the browser sends the diary_auth cookie
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=EXPOSED_VERSION_HEADERS,
)


@app.middleware("http")
async def version_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    # Static asset responses (e.g. stored food images) don't need the version
    # headers and shouldn't pay for a DB read per request; skip them so their
    # own Cache-Control survives untouched.
    if path.startswith("/api") and "/images/" not in path:
        # Per-user data behind a same-origin cookie: never let the browser reuse
        # one user's API response for another (e.g. after logging out and back
        # in as someone else).
        response.headers["Cache-Control"] = "no-store"
        # Starlette's JSONResponse omits the charset; without it a UTF-8 client
        # (Ktor/Android) mis-decodes emoji/°/³ -> "illegal char in the json".
        if response.headers.get("content-type", "").strip().lower() == "application/json":
            response.headers["content-type"] = "application/json; charset=utf-8"
        user = getattr(request.state, "username", None)  # set by require_user
        for name, value in _collect_versions(user).items():
            response.headers[f"X-{name.capitalize()}-Version"] = str(value)
    elif path.startswith("/assets/") or path.startswith("/ui/assets/"):
        # Vite content-hashes these filenames, so a new build is always a new
        # URL -- safe to let the browser cache them forever.
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    elif not path.startswith("/api"):
        # The SPA shell (index.html, served here directly or as the html=True
        # fallback for client-side routes) has neither a hash nor an explicit
        # Cache-Control today, so browsers fall back to heuristic caching and
        # can keep serving a build whose bundled asset hashes no longer exist
        # -- the exact "stale Chrome, fine in Firefox" symptom seen after a
        # redeploy. Forcing revalidation on every load keeps it in sync while
        # still letting a 304 skip re-downloading the body.
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.get("/api/version", tags=["meta"])
def version(user: str = Depends(require_user)):
    return _collect_versions(user)


@app.get("/api/me", tags=["meta"])
def me(user: str = Depends(require_user)):
    """One-shot, not polled: a client calls this once (at login / app start)
    to learn what it's allowed to show, rather than every panel finding out
    the hard way from a 403 the first time it fetches its own data. null =
    unrestricted (every panel); otherwise the explicit allowed list."""
    vis = visible_panels(user)
    return {"username": user, "visible_panels": sorted(vis) if vis is not None else None}


for _mod in ROUTER_MODULES:
    panel = getattr(_mod, "PANEL", None)
    dep = require_panel(panel) if panel else require_user
    app.include_router(_mod.router, dependencies=[Depends(dep)])

if FRONTEND_DIST.is_dir():
    # The SPA is built with vite `base: "/ui/"`, so index.html asks for
    # /ui/assets/... . In production nginx strips that prefix before proxying
    # (`location /ui/ { proxy_pass .../; }`), which is why the root mount
    # below is what serves those requests there.
    #
    # Hitting this port directly — no nginx, e.g. http://localhost:8000 while
    # developing — nothing strips the prefix, so the bundle 404s and the page
    # renders blank with a correct <title>. Mounting the same directory at
    # /ui as well makes both work: the root mount keeps serving nginx's
    # stripped paths, and this one answers the /ui/... URLs the HTML actually
    # contains. Registered first because Starlette matches mounts in order
    # and the "/" mount below would otherwise swallow everything.
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa-ui")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
