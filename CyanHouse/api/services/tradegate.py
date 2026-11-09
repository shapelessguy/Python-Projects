#!/usr/bin/env python3
"""
Tradegate tick recorder.

Polls tradegatebsx.com for a list of ISINs and appends every trade (tick) to
    <API_DATA_DIR>/tradegate/<YYYY-MM-DD>/<ISIN>_trades.csv
and, with --quotes, bid/ask snapshots to
    <API_DATA_DIR>/tradegate/<YYYY-MM-DD>/<ISIN>_quotes.csv
Only TODAY lives in those CSVs. At start-up and whenever the date changes,
every earlier day is moved into the SQLite store (api/services/tradegate_store.py,
<API_DATA_DIR>/tradegate.db) and its CSVs are deleted.

The watched ISINs are the union of all users' watchlists in that store,
re-read every cycle, so a stock added for any user is picked up without a
restart. Manage them with
    python -m api.services.tradegate_store watch <user> <ISIN> [...]
(API_DATA_DIR comes from api.config; by default data/api/data/.)

Request strategy (keeps load on the site low):
  * Stocks that belong to one of Tradegate's index lists (DAX, MDAX, SDAX,
    TecDAX, Euro Stoxx 50, US list) are watched through ONE request per index
    per cycle. The trades endpoint is only called for a stock when its trade
    count went up.
  * Any other stock is polled directly: one request per stock per cycle,
    asking only for trades after the last one already saved.

On start it backfills the whole current day, and it resumes from the CSV
files if restarted. Standard library only, Python 3.8+.

The API runs this loop in a background thread (api/routers/stocks.py), so
normally nothing has to be started by hand; the folder lock keeps a second
copy from the CLI from writing alongside it.

Usage (from the project root, the folder holding api/):
    python -m api.services.tradegate                 # all users' watchlists
    python -m api.services.tradegate DE0005140008    # only these ISINs (testing)
    python -m api.services.tradegate --interval 10 --quotes

Note: this uses the JSON endpoints behind Tradegate's public web pages, not an
official API. Check their terms of use and keep the interval reasonable.
"""

import argparse
import csv
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

from api.services import tradegate_store as store
from api.services.tradegate_store import TRADEGATE_DIR

BASE = "https://www.tradegatebsx.com/"
USER_AGENT = "Mozilla/5.0 (tradegate-tick-recorder)"
REQUEST_GAP = 0.3         # seconds between consecutive requests

# Index lists published by Tradegate (index ISIN -> label)
INDEX_FEEDS = {
    "DE000A1EXRV0": "DAX",
    "DE000A1EXRW8": "MDAX",
    "DE000A1EXRX6": "SDAX",
    "DE000A1EXRY4": "TecDAX",
    "EU0009658145": "EuroStoxx50",
    "US0000000002": "US",
}

TRADE_FIELDS = ["trade_id", "date", "time", "price", "size"]
QUOTE_FIELDS = ["timestamp", "bid", "ask", "trades_today"]


# ----------------------------------------------------------------- helpers

def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def to_float(value):
    """Tradegate mixes JSON numbers and German strings like '1 234,56'."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("\xa0", "").replace(" ", "").replace("%", "")
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except ValueError:
        return None


_last_request = 0.0


def fetch_json(path, retries=3):
    """GET a Tradegate JSON endpoint. Returns None for an empty body."""
    global _last_request
    for attempt in range(1, retries + 1):
        wait = REQUEST_GAP - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("latin-1").strip()
            if not body:
                return None
            if body.startswith("<"):           # HTML error/landing page
                raise ValueError("got HTML instead of JSON")
            return json.loads(body)
        except (urllib.error.URLError, ValueError, TimeoutError, ConnectionError) as e:
            if attempt == retries:
                log(f"  ! {path}: {e}")
                return None
            time.sleep(2 * attempt)


def append_rows(path, fields, rows):
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(fields)
        w.writerows(rows)


def last_saved_id(path):
    """Highest trade_id already in a CSV (0 if none) -> lets us resume."""
    if not os.path.exists(path):
        return 0
    best = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                best = max(best, int(row["trade_id"]))
            except (KeyError, ValueError):
                pass
    return best


# ----------------------------------------------------------------- recorder

class Stock:
    def __init__(self, isin):
        self.isin = isin
        self.name = ""
        self.index = None        # index ISIN it is watched through, or None
        self.last_id = 0         # last trade id saved today
        self.last_count = -1     # trade count seen in the index feed


class Recorder:
    def __init__(self, isins, out_dir, quotes):
        self.stocks = {i: Stock(i) for i in isins}
        self.out_dir = out_dir
        self.quotes = quotes
        self.day = None

    def sync_watchlist(self, isins):
        """Add/drop stocks to match the current watchlists."""
        isins = set(isins)
        added = [i for i in isins if i not in self.stocks]
        removed = [i for i in self.stocks if i not in isins]
        for i in removed:
            del self.stocks[i]
            log(f"{i}  no longer on any watchlist")
        if added:
            new = {i: Stock(i) for i in added}
            self.assign_indexes(new)
            for st in new.values():
                if self.day:
                    st.last_id = last_saved_id(self.trades_path(st.isin))
            self.stocks.update(new)

    # -- files
    def trades_path(self, isin):
        return os.path.join(self.out_dir, self.day, f"{isin}_trades.csv")

    def quotes_path(self, isin):
        return os.path.join(self.out_dir, self.day, f"{isin}_quotes.csv")

    # -- setup
    def assign_indexes(self, stocks=None):
        """Find which index feed (if any) lists each stock."""
        stocks = self.stocks if stocks is None else stocks
        wanted = set(stocks)
        for ix, label in INDEX_FEEDS.items():
            if not wanted:
                break
            data = fetch_json(f"json/indizes-{ix}.json")
            if not data or "indizes" not in data:
                continue
            for row in data["indizes"]:
                isin = row.get("isin")
                if isin in wanted:
                    st = stocks[isin]
                    st.index = ix
                    st.name = html.unescape(row.get("name", ""))
                    wanted.discard(isin)
        for st in stocks.values():
            via = INDEX_FEEDS[st.index] if st.index else "direct"
            log(f"{st.isin}  {st.name:35s} via {via}")

    def start_day(self):
        self.day = datetime.now().strftime("%Y-%m-%d")
        try:
            store.migrate_past_days(self.out_dir, log=log)
        except Exception as e:   # never stop recording because of the DB
            log(f"  ! migrating past days failed, will retry tomorrow/next start: {e}")
        for st in self.stocks.values():
            st.last_id = last_saved_id(self.trades_path(st.isin))
            st.last_count = -1
        log(f"--- trading day {self.day} ---")

    # -- trades
    def pull_trades(self, st, target=None):
        """Fetch all trades after st.last_id and save them.

        Pages are not a fixed size, so keep asking until a page brings nothing
        new, or until we reach `target` (the trade count from the index feed).
        A page can hold only order-book records and no trade (a busy stock's
        first page in the morning: one record), so the next page is asked
        after the page's last record, whatever it is.
        """
        total = 0
        cursor = st.last_id
        while target is None or cursor < target:
            data = fetch_json(f"umsaetze.php?isin={st.isin}&id={cursor}")
            if not data:
                break
            ids = [int(rec["id"]) for rec in data if str(rec.get("id", "")).isdigit()]
            if not ids or max(ids) <= cursor:
                break
            cursor = max(ids)
            rows = []
            for rec in data:
                # Records carrying 'umsatz' are executed trades; the rest are
                # order-book bookkeeping used by the website.
                if "umsatz" not in rec:
                    continue
                tid = int(rec["id"])
                if tid <= st.last_id:
                    continue
                rows.append([tid, rec.get("date", self.day), rec.get("time", ""),
                             to_float(rec.get("price")), to_float(rec.get("umsatz"))])
            if rows:
                rows.sort(key=lambda r: r[0])
                append_rows(self.trades_path(st.isin), TRADE_FIELDS, rows)
                st.last_id = rows[-1][0]
                total += len(rows)
        if total:
            log(f"  {st.isin} +{total} trades (last id {st.last_id})")
        return total

    # -- one polling cycle
    def cycle(self):
        """One pass over every stock. Returns {isin: trades saved} for the
        stocks that got any."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        added = {}

        # 1) stocks covered by an index feed: one request per index
        for ix in sorted({s.index for s in self.stocks.values() if s.index}):
            data = fetch_json(f"json/indizes-{ix}.json")
            if not data or "indizes" not in data:
                continue
            for row in data["indizes"]:
                st = self.stocks.get(row.get("isin"))
                if not st or st.index != ix:
                    continue
                count = int(row.get("count") or 0)
                if self.quotes:
                    append_rows(self.quotes_path(st.isin), QUOTE_FIELDS,
                                [[now, to_float(row.get("bid")), to_float(row.get("ask")), count]])
                if count < st.last_id:          # counter reset -> new day started
                    st.last_id = 0
                if count > st.last_id and (n := self.pull_trades(st, target=count)):
                    added[st.isin] = n
                st.last_count = count

        # 2) other stocks: ask directly for trades after the last saved one
        for st in self.stocks.values():
            if st.index:
                continue
            if self.quotes:
                q = fetch_json(f"refresh.php?isin={st.isin}")
                if q:
                    append_rows(self.quotes_path(st.isin), QUOTE_FIELDS,
                                [[now, to_float(q.get("bid")), to_float(q.get("ask")),
                                  q.get("executions")]])
            if n := self.pull_trades(st):
                added[st.isin] = n
        return added


# ----------------------------------------------------------------- main

def in_trading_window(window):
    now = datetime.now()
    if now.weekday() >= 5:      # Saturday / Sunday
        return False
    start, end = window.split("-")
    hhmm = now.strftime("%H:%M")
    return start <= hhmm <= end


class RecorderBusy(RuntimeError):
    pass


def acquire_lock(out_dir):
    """Allow only one recorder per output folder: two would each append the
    same trades. The OS releases the lock when the process exits, even on a
    crash. Returns the open lock file (keep a reference) or raises RecorderBusy."""
    os.makedirs(out_dir, exist_ok=True)
    f = open(os.path.join(out_dir, ".lock"), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RecorderBusy(f"Another tradegate recorder is already writing to {out_dir}. Stop it first.")
    return f


def run(isins=(), out=str(TRADEGATE_DIR), interval=30, quotes=False, hours="07:25-22:10",
        once=False, on_trades=None):
    """The recorder loop: the CLI below, and the API's background thread
    (api/routers/stocks.py), which passes `on_trades({isin: n})` to hear
    which stocks got new trades.
    Raises RecorderBusy if another recorder holds the folder."""
    fixed = [store.normalise_isin(i) for i in isins]

    def wanted():
        if fixed:
            return fixed
        try:
            return store.all_watched()
        except Exception as e:
            log(f"  ! reading watchlists failed: {e}")
            return list(rec.stocks)            # keep what we have

    lock = acquire_lock(out)  # noqa: F841  (held until exit)
    rec = Recorder([], out, quotes)
    rec.start_day()                            # migrates finished days first
    rec.sync_watchlist(wanted())
    if not rec.stocks:
        log("no ISINs on any watchlist yet -- add some with "
            "'python -m api.services.tradegate_store watch <user> <ISIN>'")

    while True:
        if datetime.now().strftime("%Y-%m-%d") != rec.day:
            rec.start_day()
        rec.sync_watchlist(wanted())
        if once or in_trading_window(hours):
            t0 = time.monotonic()
            added = rec.cycle()
            if added and on_trades:
                on_trades(added)
            if once:
                break
            time.sleep(max(1.0, interval - (time.monotonic() - t0)))
        else:
            time.sleep(60)


def main():
    p = argparse.ArgumentParser(description="Record Tradegate trades (ticks) for all watched ISINs.")
    p.add_argument("isins", nargs="*",
                   help="only these ISINs (default: the union of all users' watchlists)")
    p.add_argument("--out", default=str(TRADEGATE_DIR), help="output folder (default: %(default)s)")
    p.add_argument("--interval", type=float, default=30, help="seconds between cycles (default: 30)")
    p.add_argument("--quotes", action="store_true", help="also record bid/ask snapshots each cycle")
    p.add_argument("--hours", default="07:25-22:10",
                   help="local time window to poll, Mon-Fri (default: 07:25-22:10)")
    p.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = p.parse_args()
    try:
        run(args.isins, args.out, args.interval, args.quotes, args.hours, args.once)
    except RecorderBusy as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        log("stopped")


if __name__ == "__main__":
    main()
