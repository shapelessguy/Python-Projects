"""Hourly precipitation forecasts from two independent, keyless providers.

Each fetcher returns a DataFrame indexed by a naive *local-time* ``datetime``
(hourly) with two columns:

    precip_mm    float  — precipitation total in that hour (mm)
    precip_prob  float  — probability of precipitation in that hour (0-100),
                          NaN when the provider doesn't give one

open-meteo : global multi-model blend, ~16 days.   api.open-meteo.com
dwd        : DWD MOSMIX via Bright Sky, ~10 days.   api.brightsky.dev

Kept free of any ``api`` import so the package stays usable on its own, like
``utilities``.
"""
import pandas as pd
import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
BRIGHTSKY_URL = "https://api.brightsky.dev/weather"

_TIMEOUT = 60


def fetch_open_meteo(coords: tuple[float, float], forecast_days: int = 16) -> pd.DataFrame:
    lat, lon = coords
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation,precipitation_probability",
        "timezone": "auto",          # -> timestamps are naive local wall time
        "forecast_days": forecast_days,
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    h = r.json()["hourly"]
    df = pd.DataFrame({
        "datetime":    pd.to_datetime(h["time"]),
        "precip_mm":   pd.to_numeric(pd.Series(h.get("precipitation")), errors="coerce"),
        "precip_prob": pd.to_numeric(pd.Series(h.get("precipitation_probability")), errors="coerce"),
    }).set_index("datetime")
    return df.sort_index()


def fetch_dwd(coords: tuple[float, float], tz: str = "Europe/Berlin") -> pd.DataFrame:
    """DWD MOSMIX point forecast through Bright Sky. Requests a 10-day window
    starting today; ``tz`` makes Bright Sky return timestamps on that offset,
    which we strip to naive local so the index lines up with Open-Meteo's."""
    lat, lon = coords
    today = pd.Timestamp.now(tz=tz).normalize()
    params = {
        "lat":       lat,
        "lon":       lon,
        "date":      today.date().isoformat(),
        "last_date": (today + pd.Timedelta(days=10)).date().isoformat(),
        "tz":        tz,
    }
    r = requests.get(BRIGHTSKY_URL, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    rows = r.json().get("weather", [])
    if not rows:
        return pd.DataFrame(columns=["precip_mm", "precip_prob"]).rename_axis("datetime")

    src = pd.DataFrame(rows)
    if "precipitation" not in src:
        src["precipitation"] = float("nan")
    if "precipitation_probability" not in src:
        src["precipitation_probability"] = float("nan")
    idx = (
        pd.to_datetime(src["timestamp"], utc=True)
        .dt.tz_convert(tz)
        .dt.tz_localize(None)
    )
    out = pd.DataFrame({
        "precip_mm":   pd.to_numeric(src["precipitation"], errors="coerce"),
        "precip_prob": pd.to_numeric(src["precipitation_probability"], errors="coerce"),
    })
    out.index = idx
    out.index.name = "datetime"
    return out[~out.index.duplicated(keep="first")].sort_index()
