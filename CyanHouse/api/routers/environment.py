import threading

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from api.db import bump, connect, get_version
from api.services import weather

router = APIRouter(prefix="/api/environment", tags=["environment"])


def init() -> None:
    """A fresh deployment starts with no historical weather CSVs at all —
    min_date/max_date come back null, the date-range presets silently do
    nothing, and the plot never renders. Fetch once in the background at
    startup so that's populated without needing someone to know to hit
    /refresh manually. update_city (what this calls into) is incremental and
    a no-op once a city is already current, so this is cheap on every
    restart after the first."""
    def run() -> None:
        try:
            weather.refresh()
            with connect() as conn:
                bump(conn, "weather_version")
        except Exception as e:
            print(f"[environment] startup weather fetch failed: {e}")

    threading.Thread(target=run, name="weather-startup-fetch", daemon=True).start()


@router.get("/bootstrap")
def bootstrap():
    data = weather.bootstrap()
    with connect() as conn:
        data["weather_version"] = get_version(conn, "weather_version")
    return data


@router.get("/series")
def series(
    cities: str = Query(..., description="comma-separated city keys"),
    start: str = Query(...),
    end: str = Query(...),
    resample: str = Query("daily", pattern="^(hourly|daily|weekly)$"),
    vars: str = Query("", description="comma-separated variable keys"),
):
    return weather.get_series(
        [c for c in cities.split(",") if c],
        start, end, resample,
        [v for v in vars.split(",") if v],
    )


@router.post("/refresh")
async def refresh():
    await run_in_threadpool(weather.refresh)
    with connect() as conn:
        version = bump(conn, "weather_version")
    # full fresh state in the reply — cities, variables, available range
    return {"weather_version": version, **weather.bootstrap()}
