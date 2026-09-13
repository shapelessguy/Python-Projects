import importlib
import pkgutil
import sys
import os
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import variables as variables
from utilities.base import WeatherVariable
from monitor_md import CITIES, START_DATE

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv(path: str) -> None:
    """Minimal .env reader, duplicated from api/config.py so this module reads
    DATA_DIR too when run standalone (python utilities/update_data.py)."""
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
DATASETS_DIR = os.path.join(_data_dir or _PROJECT_DIR, "utilities", "datasets")


# ── Discovery ───────────────────────────────────────────────────────────────
def discover_variables() -> list[type[WeatherVariable]]:
    for _, mod_name, _ in pkgutil.iter_modules(variables.__path__):
        importlib.import_module(f"variables.{mod_name}")
    return WeatherVariable.__subclasses__()


# ── Download ────────────────────────────────────────────────────────────────
def download_all(city: dict, start_date: str, end_date: str) -> pd.DataFrame:
    frames = []
    for VarClass in discover_variables():
        instance = VarClass()
        print(f"  [{city['city_name']}] Downloading {VarClass.__name__}...")
        df = instance.download(city, start_date, end_date)
        if df.empty:
            print(f"    -> skipped (not available for {city['country']})")
            continue
        print(f"    -> {len(df)} rows, {len(df.columns)} columns")
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, axis=1, join="outer")
    merged = _dedupe(merged)
    merged.index.name = "datetime"
    return merged


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate column names and duplicate timestamps, sorted. Guards
    pd.concat, which raises `InvalidIndexError: Reindexing only valid with
    uniquely valued Index objects` if either axis has duplicates — from a
    hand-edited CSV or a variable download that repeats a column name."""
    if df.empty:
        return df
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    df = df[~df.index.duplicated(keep="first")]
    return df.sort_index()


# ── CSV path ────────────────────────────────────────────────────────────────
def csv_path(city: dict) -> str:
    name = city["city_name"].lower().replace(" ", "_")
    return os.path.join(DATASETS_DIR, f"{name}_weather.csv")


# ── Update one city ─────────────────────────────────────────────────────────
def update_city(city: dict):
    output = csv_path(city)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    yesterday = str(date.today() - timedelta(days=1))

    if os.path.exists(output):
        existing = pd.read_csv(output, index_col="datetime", parse_dates=True)
        last_dt = existing.index.max().date()
        if str(last_dt) >= yesterday:
            print(f"[{city['city_name']}] Already up to date.")
            return  # leave the stored file untouched
        start = str(last_dt + timedelta(days=1))
        print(f"[{city['city_name']}] Fetching {start} → {yesterday}...")
        fresh = _dedupe(download_all(city, start, yesterday))
        # A refresh only ever APPENDS. Keep just the rows strictly newer than
        # what we already have: a download that returns a wider range (possibly
        # NaN-filled for older dates) must never overwrite stored history.
        if not fresh.empty:
            fresh = fresh.loc[fresh.index > existing.index.max()]
        if fresh.empty:
            print(f"[{city['city_name']}] No new rows.")
            return
        updated = pd.concat([existing, fresh])
        updated = updated.loc[:, ~updated.columns.duplicated(keep="first")]
        updated = updated[~updated.index.duplicated(keep="first")].sort_index()
        updated.index.name = "datetime"
        updated.to_csv(output)
        print(f"[{city['city_name']}] Appended {len(fresh)} rows. Total: {len(updated)} rows.")
    else:
        print(f"[{city['city_name']}] Building from scratch ({START_DATE} → {yesterday})...")
        merged = download_all(city, START_DATE, yesterday)
        if city["country"] == "Germany":
            merged = merged[merged.index >= START_DATE]
        merged = _dedupe(merged)
        if merged.empty:
            # A transient fetch failure (network hiccup, source down) must
            # never create the file at all — an empty file on disk would
            # then look "already built" to every caller (_read_csv treats
            # missing vs. empty the same, but only if the path never got
            # created in the first place) and silently stay broken forever.
            print(f"[{city['city_name']}] No data returned — leaving unfetched, will retry next time.")
            return
        merged.to_csv(output)
        print(f"[{city['city_name']}] Saved {len(merged)} rows × {len(merged.columns)} columns.")


def update():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", help="Update only this city (case-insensitive city_name)")
    args = parser.parse_args()

    targets = CITIES
    if args.city:
        targets = [c for c in CITIES if c["city_name"].lower() == args.city.lower()]
        if not targets:
            print(f"Unknown city '{args.city}'. Available: {[c['city_name'] for c in CITIES]}")

    for city in targets:
        update_city(city)

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    update()