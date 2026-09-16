"""Precipitation-forecast service — a plug-and-play router module (see food.py).

Open-Meteo covers the whole ~16-day horizon; DWD (MOSMIX via Bright Sky) is
overlaid on the first 72 h for German cities. A daemon thread re-fetches every
``FORECAST_POLL_SECONDS`` and bumps ``forecast`` so the 1 Hz ``/api/version``
poll pulls the update through to every client. The counter is global (like
``weather``) — the forecast is the same for everyone.

Contract picked up by ``api/main.py`` auto-discovery:
  * ``router``          — mounted under /api/forecast
  * ``VERSION_NAMES``   — ["forecast"], added to /api/version + X-Forecast-Version
  * ``init()``          — start the background poller
  * ``versions(user)``  — current global counter
"""
from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from api.config import FORECAST_POLL_SECONDS
from api.db import bump, connect, get_version
from api.services import forecast
from forecast import update

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

VERSION_NAMES = ["forecast"]
# Embedded inside EnvironmentPanel (ForecastStrip), not its own tab -- shares
# that panel's visibility gate. See api/auth.py.
PANEL = "environment"

_KEY = "forecast_version"


def _bump() -> int:
    with connect() as conn:
        return bump(conn, _KEY)


def init() -> None:
    # Single-worker dev server: one poller. Under multiple uvicorn workers each
    # would poll — harmless (same cache file, atomic replace) but wasteful.
    update.start_poller(_bump, FORECAST_POLL_SECONDS)


def versions(user: str | None) -> dict[str, int]:
    try:
        with connect() as conn:
            return {"forecast": get_version(conn, _KEY)}
    except Exception:
        return {"forecast": 0}


@router.get("/bootstrap")
def bootstrap():
    data = forecast.bootstrap()
    with connect() as conn:
        data["forecast_version"] = get_version(conn, _KEY)
    return data


@router.get("/series")
def series(cities: str = Query(..., description="comma-separated city keys")):
    return forecast.get_forecast([c for c in cities.split(",") if c])


@router.get("/overview")
def overview(
    city: str = Query(..., description="city key"),
    range_: str = Query("today", alias="range", pattern="^(today|week)$"),
):
    return forecast.get_overview(city, range_)


@router.post("/refresh")
async def refresh():
    await run_in_threadpool(forecast.refresh)
    version = _bump()
    return {"forecast_version": version, **forecast.bootstrap()}
