"""Hourly weather forecasts from two independent, keyless providers.

Each fetcher returns a DataFrame indexed by a naive *local-time* ``datetime``
(hourly) with these columns (NaN when the provider doesn't give one):

    precip_mm        float  — precipitation total in that hour (mm)
    precip_prob      float  — probability of precipitation in that hour (0-100)
    temperature_c     float  — air temperature (°C)
    wind_speed_kmh     float  — wind speed (km/h)
    cloud_cover_pct    float  — total cloud cover (0-100)
    humidity_pct       float  — relative humidity (0-100)

``fetch_open_meteo`` also returns that day's sunrise/sunset (needed to work
out how much daylight an overview segment gets) as a bonus second value,
since Open-Meteo can hand back both the hourly and the daily block in one
request. DWD has no equivalent (astronomical, not model-dependent), so
there's a single sun-times source for every city regardless of country.

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

OPEN_METEO_HOURLY = (
    "precipitation,precipitation_probability,temperature_2m,"
    "wind_speed_10m,cloud_cover,relative_humidity_2m"
)
_OPEN_METEO_COLUMNS = {
    "precipitation": "precip_mm",
    "precipitation_probability": "precip_prob",
    "temperature_2m": "temperature_c",
    "wind_speed_10m": "wind_speed_kmh",
    "cloud_cover": "cloud_cover_pct",
    "relative_humidity_2m": "humidity_pct",
}
_BRIGHTSKY_COLUMNS = {
    "precipitation": "precip_mm",
    "precipitation_probability": "precip_prob",
    "temperature": "temperature_c",
    "wind_speed": "wind_speed_kmh",
    "cloud_cover": "cloud_cover_pct",
    "relative_humidity": "humidity_pct",
}
METRIC_COLUMNS = list(_OPEN_METEO_COLUMNS.values())
OPEN_METEO_DAILY = "sunrise,sunset"


def fetch_open_meteo(
    coords: tuple[float, float], forecast_days: int = 16
) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    """Returns (hourly_df, sun_by_date). ``sun_by_date`` maps an ISO date
    ("YYYY-MM-DD") to {"sunrise": iso, "sunset": iso}, both naive local
    timestamps like the hourly index."""
    lat, lon = coords
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": OPEN_METEO_HOURLY,
        "daily": OPEN_METEO_DAILY,
        "timezone": "auto",          # -> timestamps are naive local wall time
        "forecast_days": forecast_days,
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    body = r.json()
    h = body["hourly"]
    df = pd.DataFrame({
        "datetime": pd.to_datetime(h["time"]),
        **{
            col: pd.to_numeric(pd.Series(h.get(src)), errors="coerce")
            for src, col in _OPEN_METEO_COLUMNS.items()
        },
    }).set_index("datetime")

    daily = body.get("daily", {})
    sun = {
        date: {"sunrise": sunrise, "sunset": sunset}
        for date, sunrise, sunset in zip(
            daily.get("time", []), daily.get("sunrise", []), daily.get("sunset", [])
        )
    }
    return df.sort_index(), sun


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
        return pd.DataFrame(columns=METRIC_COLUMNS).rename_axis("datetime")

    src = pd.DataFrame(rows)
    idx = (
        pd.to_datetime(src["timestamp"], utc=True)
        .dt.tz_convert(tz)
        .dt.tz_localize(None)
    )
    out = pd.DataFrame({
        col: pd.to_numeric(src[field], errors="coerce") if field in src else float("nan")
        for field, col in _BRIGHTSKY_COLUMNS.items()
    })
    out.index = idx
    out.index.name = "datetime"
    return out[~out.index.duplicated(keep="first")].sort_index()
