"""
SQLite store for Tradegate data: everything before today.

Today's ticks are written to CSV by the recorder (api/services/tradegate.py)
because it appends every few seconds. Once a day is over, migrate_past_days()
moves each finished day's CSVs into the database and deletes them. It runs:
  * when the recorder starts and when it sees the date change,
  * at the start of the daily-history job (api/services/tradegate_history.py),
  * by hand:  python -m api.services.tradegate_store
It is idempotent (INSERT OR IGNORE on the primary keys), so a crash halfway
through just redoes the work next time.

Per-user access: market data is stored once (a trade is the same for everyone),
and each user's `watchlist` decides which ISINs they may read. The recorder
and the history job collect the union of all watchlists. Every read function
here takes the username and returns nothing for ISINs not on that user's list.

Database: <API_DATA_DIR>/tradegate.db  (own file, like food.db)
  watchlist    which user follows which ISIN         PK (username, isin)
  trades       one row per Tradegate trade           PK (isin, date, trade_id)
  quotes       bid/ask snapshots (recorder --quotes) PK (isin, ts)
  daily        daily OHLCV bars for the Tradegate venue PK (isin, date)
  instruments  onvista lookup cache for the history job
"""

import csv
import os
import re
import shutil
from datetime import date

from api.config import API_DATA_DIR
from api.db import connect

TRADEGATE_DB = API_DATA_DIR / "tradegate.db"
TRADEGATE_DIR = API_DATA_DIR / "tradegate"

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    username TEXT NOT NULL,
    isin     TEXT NOT NULL,
    added    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (username, isin)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS watchlist_isin ON watchlist (isin);

CREATE TABLE IF NOT EXISTS trades (
    isin     TEXT    NOT NULL,
    date     TEXT    NOT NULL,          -- YYYY-MM-DD (German local date)
    trade_id INTEGER NOT NULL,          -- Tradegate's running number, restarts daily
    time     TEXT    NOT NULL,          -- HH:MM:SS.mmm German local time
    price    REAL    NOT NULL,
    size     REAL    NOT NULL,
    PRIMARY KEY (isin, date, trade_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS quotes (
    isin         TEXT NOT NULL,
    ts           TEXT NOT NULL,         -- YYYY-MM-DD HH:MM:SS local time of the snapshot
    bid          REAL,
    ask          REAL,
    trades_today INTEGER,
    PRIMARY KEY (isin, ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS daily (
    isin   TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL,
    high   REAL,
    low    REAL,
    close  REAL,
    volume REAL,
    trades INTEGER,
    PRIMARY KEY (isin, date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS instruments (
    isin       TEXT PRIMARY KEY,
    type       TEXT NOT NULL,           -- onvista entity type (STOCK, FUND, ...)
    onvista_id TEXT NOT NULL,
    notation   INTEGER NOT NULL,        -- onvista id of the Tradegate listing
    name       TEXT
);
"""

_DAY_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_initialised = False


def db():
    """Connection context manager (commit on success, rollback on error)."""
    global _initialised
    if not _initialised:
        os.makedirs(API_DATA_DIR, exist_ok=True)
        with connect(TRADEGATE_DB) as conn:
            conn.execute("PRAGMA journal_mode = WAL")   # readers don't block the writer
            conn.executescript(SCHEMA)
        _initialised = True
    return connect(TRADEGATE_DB)


# ----------------------------------------------------------------- CSV -> DB

def _num(s):
    return float(s) if s not in (None, "", "None") else None


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def migrate_day(day_dir, log=print):
    """Move one finished day's CSVs into the DB, then delete the folder."""
    day = os.path.basename(day_dir)
    files = sorted(os.listdir(day_dir))
    moved = 0
    with db() as conn:
        for name in files:
            path = os.path.join(day_dir, name)
            if name.endswith("_trades.csv"):
                isin = name[: -len("_trades.csv")]
                rows = [(isin, day, int(r["trade_id"]), r["time"],
                         _num(r["price"]), _num(r["size"])) for r in _read_csv(path)]
                conn.executemany("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?)", rows)
                # verify before deleting anything
                ids = {r[2] for r in rows}
                stored = conn.execute("SELECT COUNT(*) FROM trades WHERE isin=? AND date=?",
                                      (isin, day)).fetchone()[0]
                if stored < len(ids):
                    raise RuntimeError(f"{path}: {len(ids)} trades in CSV, only {stored} in DB")
                moved += len(ids)
            elif name.endswith("_quotes.csv"):
                isin = name[: -len("_quotes.csv")]
                rows = [(isin, r["timestamp"], _num(r["bid"]), _num(r["ask"]),
                         int(_num(r["trades_today"]) or 0)) for r in _read_csv(path)]
                conn.executemany("INSERT OR IGNORE INTO quotes VALUES (?,?,?,?,?)", rows)
    # committed (the with-block exited cleanly) -> safe to delete the CSVs
    shutil.rmtree(day_dir)
    log(f"migrated {day}: {moved} trades from {len(files)} files into {TRADEGATE_DB.name}")
    return moved


def migrate_past_days(out_dir=TRADEGATE_DIR, today=None, log=print):
    """Migrate every YYYY-MM-DD folder older than today. Returns trades moved."""
    today = (today or date.today()).isoformat()
    if not os.path.isdir(out_dir):
        return 0
    total = 0
    for name in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, name)
        if _DAY_DIR.match(name) and name < today and os.path.isdir(path):
            total += migrate_day(path, log=log)
    return total


# ----------------------------------------------------------------- daily bars

def last_daily_date(isin):
    with db() as conn:
        row = conn.execute("SELECT MAX(date) FROM daily WHERE isin=?", (isin,)).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None


def save_daily(isin, rows):
    """rows: [date_iso, open, high, low, close, volume, trades]"""
    with db() as conn:
        conn.executemany("INSERT OR REPLACE INTO daily VALUES (?,?,?,?,?,?,?,?)",
                         [(isin, *r) for r in rows])


def get_instrument(isin):
    with db() as conn:
        row = conn.execute("SELECT * FROM instruments WHERE isin=?", (isin,)).fetchone()
    return dict(row) if row else None


def save_instrument(isin, info):
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO instruments VALUES (?,?,?,?,?)",
                     (isin, info["type"], info["onvista_id"], info["notation"], info["name"]))


# ----------------------------------------------------------------- watchlists

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def normalise_isin(isin):
    isin = isin.strip().upper()
    if not _ISIN.match(isin):
        raise ValueError(f"not an ISIN: {isin!r}")
    return isin


def watchlist(user):
    with db() as conn:
        return [r[0] for r in conn.execute(
            "SELECT isin FROM watchlist WHERE username=? ORDER BY added, isin", (user,))]


def watch(user, isins):
    with db() as conn:
        conn.executemany("INSERT OR IGNORE INTO watchlist (username, isin) VALUES (?,?)",
                         [(user, normalise_isin(i)) for i in isins])


def unwatch(user, isins):
    """Removes from the user's list only; the market data stays for others."""
    with db() as conn:
        conn.executemany("DELETE FROM watchlist WHERE username=? AND isin=?",
                         [(user, normalise_isin(i)) for i in isins])


def all_watched():
    """Union of every user's watchlist: what the recorder/history job collect."""
    with db() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT isin FROM watchlist ORDER BY isin")]


def _may_read(conn, user, isin):
    return conn.execute("SELECT 1 FROM watchlist WHERE username=? AND isin=?",
                        (user, isin)).fetchone() is not None


# ----------------------------------------------------------------- user-scoped reads

def read_daily(user, isin, start=None, end=None):
    """Daily bars for one ISIN, only if it is on this user's watchlist."""
    with db() as conn:
        if not _may_read(conn, user, isin):
            return []
        return [dict(r) for r in conn.execute(
            "SELECT date, open, high, low, close, volume, trades FROM daily "
            "WHERE isin=? AND date >= ? AND date <= ? ORDER BY date",
            (isin, start or "0000", end or "9999"))]


def read_trades(user, isin, day):
    """All stored trades of one past day, only if on this user's watchlist.
    (Today's trades are still in the recorder's CSV until the day is over.)"""
    with db() as conn:
        if not _may_read(conn, user, isin):
            return []
        return [dict(r) for r in conn.execute(
            "SELECT trade_id, time, price, size FROM trades "
            "WHERE isin=? AND date=? ORDER BY trade_id", (isin, day))]


# ----------------------------------------------------------------- CLI

def _cli():
    import argparse
    p = argparse.ArgumentParser(description="Tradegate store: watchlists and day migration.")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("migrate", help="move finished days' CSVs into the DB (default)")
    for name in ("watch", "unwatch"):
        s = sub.add_parser(name, help=f"{name} ISINs for a user")
        s.add_argument("user")
        s.add_argument("isins", nargs="+")
    s = sub.add_parser("list", help="show watchlists")
    s.add_argument("user", nargs="?")
    args = p.parse_args()

    if args.cmd == "watch":
        watch(args.user, args.isins)
    elif args.cmd == "unwatch":
        unwatch(args.user, args.isins)
    if args.cmd in ("watch", "unwatch", "list"):
        with db() as conn:
            q = "SELECT username, isin FROM watchlist"
            rows = conn.execute(q + (" WHERE username=?" if getattr(args, "user", None) else "")
                                + " ORDER BY username, isin",
                                (args.user,) if getattr(args, "user", None) else ()).fetchall()
        for r in rows:
            print(f"{r[0]:15s} {r[1]}")
        if not rows:
            print("(empty)")
        return
    n = migrate_past_days()
    print(f"done, {n} trades migrated" if n else "nothing to migrate")


if __name__ == "__main__":
    _cli()
