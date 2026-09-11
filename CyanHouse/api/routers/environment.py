from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from api.db import bump, connect, get_version
from api.services import weather

router = APIRouter(prefix="/api/environment", tags=["environment"])


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
