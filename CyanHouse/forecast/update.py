"""Build and cache the merged precipitation forecast for every city.

Merge rule
----------
Open-Meteo covers the whole ~16-day horizon. For German cities the first
``DWD_HOURS`` hours are replaced with DWD (MOSMIX via Bright Sky) wherever DWD
has a value; every row keeps a ``source`` tag ("dwd" / "open-meteo") so the UI
can show which provider it came from.

Cache layout (one pair per city, fully overwritten on every poll), under
DATASETS_DIR (<DATA_DIR or project root>/forecast/datasets by default):
    <city>_forecast.csv        datetime,precip_mm,precip_prob,source
    <city>_forecast.meta.json  {issued_at, dwd_until, sources}

Kept free of any ``api`` import; the API layer drives the poller and owns the
version counter.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

import pandas as pd

from forecast import sources
from monitor_md import CITIES

DWD_HOURS = 72

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv(path: str) -> None:
    """Minimal .env reader, duplicated from api/config.py so this module reads
    DATA_DIR too without importing `api` (see module docstring)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.split("#", 1)[0].strip())


_load_dotenv(os.path.join(_PROJECT_DIR, ".env"))
_data_dir = os.environ.get("DATA_DIR", "").strip()
DATASETS_DIR = os.path.join(_data_dir or _PROJECT_DIR, "forecast", "datasets")


def city_key(city: dict) -> str:
    return city["city_name"].lower().replace(" ", "_")


def csv_path(city: dict) -> str:
    return os.path.join(DATASETS_DIR, f"{city_key(city)}_forecast.csv")


def meta_path(city: dict) -> str:
    return os.path.join(DATASETS_DIR, f"{city_key(city)}_forecast.meta.json")


# ── build ───────────────────────────────────────────────────────────────────
def build_city_forecast(city: dict) -> tuple[pd.DataFrame, dict]:
    om = sources.fetch_open_meteo(city["coords"])
    out = om.assign(source="open-meteo")
    dwd_until = None

    if city.get("country") == "Germany":
        try:
            dwd = sources.fetch_dwd(city["coords"])
        except Exception as e:  # provider hiccup -> silently fall back to Open-Meteo
            print(f"[forecast] {city['city_name']}: DWD fetch failed ({e}); Open-Meteo only")
            dwd = pd.DataFrame()

        if not dwd.empty:
            cutoff = pd.Timestamp.now().floor("h") + pd.Timedelta(hours=DWD_HOURS)
            dwd = dwd[dwd.index <= cutoff]

            full = om.index.union(dwd.index)
            out = om.reindex(full)
            d = dwd.reindex(full)
            use = d["precip_mm"].notna()
            out.loc[use, ["precip_mm", "precip_prob"]] = d.loc[use, ["precip_mm", "precip_prob"]]
            out["source"] = "open-meteo"
            out.loc[use, "source"] = "dwd"
            if use.any():
                dwd_until = out.index[use].max().isoformat()

    out = out[["precip_mm", "precip_prob", "source"]].sort_index()
    out.index.name = "datetime"
    meta = {
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dwd_until": dwd_until,
        "sources": sorted(out["source"].dropna().unique().tolist()),
    }
    return out, meta


# ── cache I/O ───────────────────────────────────────────────────────────────
def write_forecast(city: dict) -> dict:
    os.makedirs(DATASETS_DIR, exist_ok=True)
    df, meta = build_city_forecast(city)
    tmp = csv_path(city) + ".tmp"
    df.to_csv(tmp)
    os.replace(tmp, csv_path(city))  # atomic: a failed build never truncates the cache
    with open(meta_path(city), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    print(f"[forecast] {city['city_name']}: {len(df)} h cached, sources={meta['sources']}")
    return meta


def read_forecast(city: dict) -> tuple[pd.DataFrame, dict]:
    path = csv_path(city)
    if not os.path.exists(path):
        return pd.DataFrame(), {}
    df = pd.read_csv(path, index_col="datetime", parse_dates=True)
    meta: dict = {}
    if os.path.exists(meta_path(city)):
        with open(meta_path(city), encoding="utf-8") as f:
            meta = json.load(f)
    return df, meta


def refresh_all() -> None:
    """Blocking. Best-effort per city so one provider outage can't stall the rest."""
    for c in CITIES:
        try:
            write_forecast(c)
        except Exception as e:
            print(f"[forecast] {c['city_name']}: refresh failed ({e})")


# ── background poller ───────────────────────────────────────────────────────
_poller_started = False


def start_poller(on_refreshed, interval: int) -> None:
    """Daemon thread: refresh now, then every ``interval`` seconds, calling
    ``on_refreshed()`` after each successful pass so the API can bump its version
    counter. Idempotent — safe to call from a reloader that imports twice."""
    global _poller_started
    if _poller_started:
        return
    _poller_started = True

    def loop() -> None:
        while True:
            try:
                refresh_all()
                on_refreshed()
            except Exception as e:
                print(f"[forecast] poll loop error: {e}")
            time.sleep(interval)

    threading.Thread(target=loop, name="forecast-poller", daemon=True).start()


if __name__ == "__main__":
    refresh_all()
