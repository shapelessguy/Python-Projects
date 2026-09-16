"""Buckets an hourly forecast (see ``forecast.sources``) into fixed 2-hour
segments and derives the attributes the Overview board needs per segment:

    temperature_c     float        — mean over the segment (°C)
    humidity_pct       float        — mean (0-100)
    cloud_cover_pct    float        — mean (0-100)
    precip_prob        float        — mean chance of rain (0-100)
    precip_mm          float        — total rain in the segment (mm)
    rain_level         int (0-5)    — precip_mm bucketed, for a bar-count icon
    wind_speed_kmh      float        — mean (km/h)
    wind_level          int (0-5)    — wind_speed_kmh bucketed
    solar_light         float (0-1)  — fraction of the segment between sunrise
                                       and sunset (needs a day's sun times)
    source              str | None   — the hourly source tag most common in
                                       the segment ("dwd" / "open-meteo")

Kept free of any ``api`` import, like the rest of this package.
"""
import pandas as pd

SEGMENT_HOURS = 2

# Upper bound (inclusive) -> level, checked in order; anything past the last
# bound gets the next level up. Both tuned to real 2h values rather than a
# meteorological standard, so the buckets actually spread out instead of
# everything piling into one or two levels. Rain's observed average sits
# around 0.6mm. Wind's average (~4) was given in m/s -- x3.6 to line up with
# wind_speed_kmh, then x2.5 again since the first pass still felt too low.
_RAIN_BOUNDS = [(0.0, 0), (0.1, 1), (0.3, 2), (0.6, 3), (1.0, 4)]  # else 5
_RAIN_LEVEL_MAX = 5
_WIND_BOUNDS = [(2.8, 0), (7.3, 1), (18.0, 2), (31.5, 3), (49.5, 4)]  # else 5
_WIND_LEVEL_MAX = 5


def _bucket(value: float, bounds: list[tuple[float, int]], top: int) -> int:
    for bound, level in bounds:
        if value <= bound:
            return level
    return top


def rain_level(precip_mm_2h: float) -> int:
    return _bucket(precip_mm_2h, _RAIN_BOUNDS, _RAIN_LEVEL_MAX)


def wind_level(wind_speed_kmh_avg: float) -> int:
    return _bucket(wind_speed_kmh_avg, _WIND_BOUNDS, _WIND_LEVEL_MAX)


def solar_light(seg_start: pd.Timestamp, seg_end: pd.Timestamp, sunrise, sunset) -> float:
    """Fraction of [seg_start, seg_end) that falls between sunrise and sunset.
    0 for a fully dark segment, 1 for a fully lit one."""
    span = (seg_end - seg_start).total_seconds()
    if sunrise is None or sunset is None or sunset <= sunrise or span <= 0:
        return 0.0
    lo = max(seg_start, sunrise)
    hi = min(seg_end, sunset)
    if hi <= lo:
        return 0.0
    return round((hi - lo).total_seconds() / span, 3)


def _mean_or_none(s: pd.Series):
    v = s.mean(skipna=True)
    return None if pd.isna(v) else round(float(v), 1)


def _summarize(
    group: pd.DataFrame, seg_start: pd.Timestamp, seg_end: pd.Timestamp, sun: dict, rain_divisor: int = 1
) -> dict:
    """One output row for an arbitrary [seg_start, seg_end) window and the
    hourly rows that fall in it. ``rain_divisor`` rescales the summed rain
    back to a per-SEGMENT_HOURS figure before bucketing it, so a window wider
    than SEGMENT_HOURS (see build_daily_averages) doesn't just pile every
    rainy window into the top rain_level."""
    day_sun = sun.get(seg_start.strftime("%Y-%m-%d"), {})
    sunrise = pd.Timestamp(day_sun["sunrise"]) if day_sun.get("sunrise") else None
    sunset = pd.Timestamp(day_sun["sunset"]) if day_sun.get("sunset") else None

    precip_mm = round(float(group["precip_mm"].sum(skipna=True)), 2)
    wind_avg = group["wind_speed_kmh"].mean(skipna=True)
    wind_kmh = None if pd.isna(wind_avg) else round(float(wind_avg), 1)
    sources_seen = group["source"].dropna()

    return {
        "start": seg_start.isoformat(),
        "end": seg_end.isoformat(),
        "temperature_c": _mean_or_none(group["temperature_c"]),
        "humidity_pct": _mean_or_none(group["humidity_pct"]),
        "cloud_cover_pct": _mean_or_none(group["cloud_cover_pct"]),
        "precip_prob": _mean_or_none(group["precip_prob"]),
        "precip_mm": precip_mm,
        "rain_level": rain_level(precip_mm / rain_divisor),
        "wind_speed_kmh": wind_kmh,
        "wind_level": 0 if wind_kmh is None else wind_level(wind_kmh),
        "solar_light": solar_light(seg_start, seg_end, sunrise, sunset),
        "source": sources_seen.mode().iat[0] if not sources_seen.empty else None,
    }


def build_segments(df: pd.DataFrame, sun: dict, days: int) -> list[dict]:
    """``df``: hourly forecast (sources.METRIC_COLUMNS + "source"), indexed by
    naive local datetime, as returned by ``forecast.update.read_forecast``.
    ``sun``: {date_iso: {"sunrise": iso, "sunset": iso}} from the cached meta.
    Returns one dict per SEGMENT_HOURS-hour bucket, starting at the first
    midnight in ``df`` and covering ``days`` calendar days."""
    if df.empty:
        return []

    start = df.index.min().normalize()
    end = start + pd.Timedelta(days=days)
    window = df[(df.index >= start) & (df.index < end)]
    if window.empty:
        return []

    return [
        _summarize(group, seg_start, seg_start + pd.Timedelta(hours=SEGMENT_HOURS), sun)
        for seg_start, group in window.groupby(window.index.floor(f"{SEGMENT_HOURS}h"))
    ]


DAILY_START_HOUR = 9
DAILY_END_HOUR = 19


def build_daily_averages(
    df: pd.DataFrame,
    sun: dict,
    days: int,
    start_hour: int = DAILY_START_HOUR,
    end_hour: int = DAILY_END_HOUR,
) -> list[dict]:
    """One dict per calendar day (not a 2h segment) -- for a multi-day view
    where 2h granularity is too much detail. Averages only the hours from
    ``start_hour`` up to (not including) ``end_hour`` -- the daytime hours,
    skipping the early morning and evening/night either side."""
    if df.empty:
        return []

    start = df.index.min().normalize()
    end = start + pd.Timedelta(days=days)
    window = df[
        (df.index >= start) & (df.index < end) & (df.index.hour >= start_hour) & (df.index.hour < end_hour)
    ]
    if window.empty:
        return []

    # How many SEGMENT_HOURS-wide buckets a start_hour->end_hour day covers,
    # so rain_level stays on the same scale as the 2h view (see _summarize).
    buckets_per_day = max(1, (end_hour - start_hour) // SEGMENT_HOURS)

    out = []
    for day, group in window.groupby(window.index.normalize()):
        seg_start = day + pd.Timedelta(hours=start_hour)
        seg_end = day + pd.Timedelta(hours=end_hour)
        out.append(_summarize(group, seg_start, seg_end, sun, rain_divisor=buckets_per_day))
    return out
