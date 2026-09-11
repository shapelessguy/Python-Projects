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
from fastapi.staticfiles import StaticFiles

from api import routers as _routers_pkg
from api.auth import require_user
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


app = FastAPI(title="Cyan House API", version="1.0.0", lifespan=lifespan)

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
    return response


@app.get("/api/version", tags=["meta"])
def version(user: str = Depends(require_user)):
    return _collect_versions(user)


for _mod in ROUTER_MODULES:
    app.include_router(_mod.router, dependencies=[Depends(require_user)])

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
