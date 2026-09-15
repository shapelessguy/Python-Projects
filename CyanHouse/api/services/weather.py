"""Read-only views over the weather CSV cache that `utilities.update_data`
maintains, plus an explicit refresh that re-downloads from DWD / Open-Meteo."""
import importlib
import os
import pkgutil

import pandas as pd

import variables as _variables_pkg
from monitor_md import CITIES
from utilities.base import WeatherVariable
from utilities.update_data import csv_path, update_city

RESAMPLE = {"hourly": None, "daily": "D", "weekly": "W"}


def city_key(c: dict) -> str:
    return c["city_name"].lower().replace(" ", "_")


_BY_KEY = {city_key(c): c for c in CITIES}


def _load_meta() -> dict:
    for _, mod_name, _ in pkgutil.iter_modules(_variables_pkg.__path__):
        importlib.import_module(f"variables.{mod_name}")
    meta: dict = {}
    for cls in WeatherVariable.__subclasses__():
        for col, info in getattr(cls, "META", {}).items():
            meta[col] = info
    return meta


def _read_csv(c: dict) -> pd.DataFrame:
    path = csv_path(c)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        # A city's file being empty (a truncated write, a failed fetch that
        # still touched the path) must not take every other city down with
        # it — treat it the same as "not fetched yet" rather than letting
        # pandas.errors.EmptyDataError bubble up out of bootstrap().
        return pd.DataFrame()
    return pd.read_csv(path, index_col="datetime", parse_dates=True)


def list_cities() -> list[dict]:
    return [
        {
            "key": city_key(c),
            "city_name": c["city_name"],
            "country": c["country"],
            "flag": c["flag"],
            "color": c["color"],
            "default": bool(c.get("default")),
        }
        for c in CITIES
    ]


def list_variables() -> list[dict]:
    meta = _load_meta()
    return [
        {
            "key": k,
            "label": v.get("label") or k,
            "unit": v.get("unit") or "",
            "group": v.get("group") or "Other",
            "default": bool(v.get("default")),
            "description": v.get("description") or "",
        }
        for k, v in meta.items()
    ]


def date_range() -> dict:
    lo, hi = None, None
    for c in CITIES:
        df = _read_csv(c)
        if df.empty:
            continue
        cmin, cmax = df.index.min().date(), df.index.max().date()
        lo = cmin if lo is None else min(lo, cmin)
        hi = cmax if hi is None else max(hi, cmax)
    return {
        "min_date": lo.isoformat() if lo else None,
        "max_date": hi.isoformat() if hi else None,
    }


def bootstrap() -> dict:
    return {"cities": list_cities(), "variables": list_variables(), **date_range()}


def get_series(city_keys: list[str], start: str, end: str, resample: str,
               var_keys: list[str]) -> dict:
    rule = RESAMPLE.get(resample, "D")
    out: dict = {}
    for ck in city_keys:
        c = _BY_KEY.get(ck)
        if c is None:
            continue
        df = _read_csv(c)
        if df.empty:
            continue
        df = df.loc[str(start):str(end)]
        if rule:
            df = df.resample(rule).mean(numeric_only=True)
        # only the requested vars this city actually has; may be empty
        wanted = [v for v in var_keys if v in df.columns] if var_keys else list(df.columns)
        series = {"index": [t.isoformat() for t in df.index]}
        for v in wanted:
            series[v] = [None if pd.isna(x) else float(x) for x in df[v]]
        out[ck] = series
    return {"resample": resample, "start": str(start), "end": str(end), "series": out}


def refresh() -> None:
    """Blocking: call from a threadpool."""
    for c in CITIES:
        update_city(c)
