"""Read-only views over the forecast CSV cache that ``forecast.update``
maintains, plus an explicit blocking refresh. Shapes the cache into the JSON the
React strip consumes; mirrors ``services/weather.py``."""
import pandas as pd

from api.services.weather import _BY_KEY, list_cities
from forecast import update


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
            "index":       [t.isoformat() for t in df.index],
            "precip_mm":   [None if pd.isna(x) else float(x) for x in df["precip_mm"]],
            "precip_prob": [None if pd.isna(x) else float(x) for x in df["precip_prob"]],
            "source":      df["source"].astype(str).tolist(),
        }
        issued[ck] = meta.get("issued_at")
    return {"issued_at": issued, "series": series}


def refresh() -> None:
    """Blocking: call from a threadpool."""
    update.refresh_all()
