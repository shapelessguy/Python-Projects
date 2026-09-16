"""Read-only views over the forecast CSV cache that ``forecast.update``
maintains, plus an explicit blocking refresh. Shapes the cache into the JSON the
React strip consumes; mirrors ``services/weather.py``."""
import pandas as pd

from api.services.weather import _BY_KEY, list_cities
from forecast import overview as _overview
from forecast import update
from forecast.sources import METRIC_COLUMNS


def _issued() -> dict:
    out = {}
    for key, c in _BY_KEY.items():
        _, meta = update.read_forecast(c)
        out[key] = meta.get("issued_at")
    return out


def bootstrap() -> dict:
    return {"cities": list_cities(), "issued_at": _issued(), "dwd_hours": update.DWD_HOURS}


def get_forecast(city_keys: list[str]) -> dict:
    series: dict = {}
    issued: dict = {}
    for ck in city_keys:
        c = _BY_KEY.get(ck)
        if c is None:
            continue
        df, meta = update.read_forecast(c)
        if df.empty:
            continue
        series[ck] = {
            "index": [t.isoformat() for t in df.index],
            **{
                # A cache file written before a metric was added to
                # METRIC_COLUMNS won't have that column yet -- it appears
                # once the next poller pass rewrites the cache.
                col: [None if pd.isna(x) else float(x) for x in df[col]] if col in df else [None] * len(df)
                for col in METRIC_COLUMNS
            },
            "source": df["source"].astype(str).tolist(),
        }
        issued[ck] = meta.get("issued_at")
    return {"issued_at": issued, "series": series}


def get_overview(city_key: str, range_: str) -> dict:
    c = _BY_KEY.get(city_key)
    if c is None:
        return {"city": city_key, "range": range_, "issued_at": None, "segments": []}
    df, meta = update.read_forecast(c)
    sun = meta.get("sun", {})
    if range_ == "week":
        # One row per day (14), not per 2h segment -- see build_daily_averages.
        segments = _overview.build_daily_averages(df, sun, days=14)
    else:
        segments = _overview.build_segments(df, sun, days=1)
    return {"city": city_key, "range": range_, "issued_at": meta.get("issued_at"), "segments": segments}


def refresh() -> None:
    """Blocking: call from a threadpool."""
    update.refresh_all()
