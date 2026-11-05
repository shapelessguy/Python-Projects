#!/usr/bin/env python3
"""
Daily price history for the Tradegate venue -> SQLite (`daily` table).

Collects every ISIN on any user's watchlist (api/services/tradegate_store.py)
and stores daily bars in <API_DATA_DIR>/tradegate.db:
    daily(isin, date, open, high, low, close, volume, trades)
Which user may read which ISIN is decided by the watchlist; this job just
fills the shared table.

Data comes from onvista's end-of-day history for the Tradegate listing
(onvista lists Tradegate as its own venue). The first run downloads everything
onvista has (stocks often back to 2004); later runs only ask for the days after
the last stored date. Only completed trading days are included.

It also moves the tick recorder's finished days into the database first, so
running this once a day (e.g. Task Scheduler / cron, after 22:30) keeps
everything before today in SQLite even if the recorder was not running.

Usage (from the project root, the folder holding api/):
    python -m api.services.tradegate_history                  # all watchlists
    python -m api.services.tradegate_history DE0005140008     # only these ISINs

Note: onvista's API is unofficial; run it once a day, not in a tight loop.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from api.services import tradegate_store as store

API = "https://api.onvista.de/api/v1/"
USER_AGENT = "Mozilla/5.0 (tradegate-history)"
REQUEST_GAP = 0.5

# onvista entity type -> path segment of its snapshot endpoint
SNAPSHOT_PATH = {"STOCK": "stocks", "FUND": "funds", "BOND": "bonds"}

# ranges onvista accepts, smallest first, with the days each one spans
RANGES = [("M1", 31), ("M3", 92), ("M6", 183), ("Y1", 366), ("Y3", 1096), ("Y5", 1827), ("Y10", 3653)]

_last_request = 0.0


def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def get_json(path):
    global _last_request
    for attempt in range(1, 4):
        wait = REQUEST_GAP - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404) or attempt == 3:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 3:
                raise
        time.sleep(2 * attempt)


def lookup(isin):
    """ISIN -> its Tradegate listing on onvista (cached in the instruments table)."""
    info = store.get_instrument(isin)
    if info:
        return info
    hits = get_json(f"instruments/query?searchValue={isin}").get("list", [])
    if not hits:
        raise LookupError("not found on onvista")
    etype, eid, name = hits[0]["entityType"], hits[0]["entityValue"], hits[0].get("name", "")
    if etype not in SNAPSHOT_PATH:
        raise LookupError(f"unsupported instrument type {etype}")
    snap = get_json(f"{SNAPSHOT_PATH[etype]}/ISIN:{isin}/snapshot")
    for q in snap.get("quoteList", {}).get("list", []):
        if q.get("market", {}).get("codeExchange") == "GAT":
            info = {"type": etype, "onvista_id": eid, "notation": q["market"]["idNotation"], "name": name}
            store.save_instrument(isin, info)
            return info
    raise LookupError("no Tradegate listing on onvista")


def fetch(info, start, range_code):
    return get_json(f"instruments/{info['type']}/{info['onvista_id']}/eod_history"
                    f"?idNotation={info['notation']}&range={range_code}&startDate={start.isoformat()}")


def to_rows(h, after):
    rows = []
    cols = [h.get(k, []) for k in ("datetimeLast", "first", "high", "low", "last", "volume", "numberPrices")]
    for ts, o, hi, lo, c, v, n in zip(*cols):
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if after is None or d > after:
            rows.append([d.isoformat(), o, hi, lo, c, v, n])
    return rows


def update(isin):
    info = lookup(isin)
    last = store.last_daily_date(isin)
    today = date.today()

    if last is None:
        # first run: find out where onvista's history starts
        probe = fetch(info, today - timedelta(days=30), "M1")
        start = datetime.fromisoformat(probe["datetimeStartAvailableHistory"][:10]).date()
    else:
        start = last + timedelta(days=1)

    added = 0
    while start < today:
        gap = (today - start).days
        code, span = next(((c, s) for c, s in RANGES if s >= gap), RANGES[-1])
        rows = to_rows(fetch(info, start, code), last)
        if rows:
            store.save_daily(isin, rows)
            last = date.fromisoformat(rows[-1][0])
            added += len(rows)
            start = last + timedelta(days=1)
        else:
            start += timedelta(days=span)   # no trading in that window (e.g. suspension)

    log(f"{isin}  {(info['name'] or '')[:35]:35s} +{added} days (up to {last})")


def main():
    p = argparse.ArgumentParser(description="Download/update daily Tradegate price history into SQLite.")
    p.add_argument("isins", nargs="*", help="only these ISINs (default: all users' watchlists)")
    args = p.parse_args()

    store.migrate_past_days(log=log)

    isins = [store.normalise_isin(i) for i in args.isins] or store.all_watched()
    if not isins:
        sys.exit("No ISINs on any watchlist. Add some with "
                 "'python -m api.services.tradegate_store watch <user> <ISIN>'.")

    failed = 0
    for isin in isins:
        try:
            update(isin)
        except Exception as e:  # keep going with the other ISINs
            failed += 1
            log(f"{isin}  ! {e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
