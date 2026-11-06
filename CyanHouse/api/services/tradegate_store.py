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
and each user's `watchlist` and `portfolio` decide which ISINs they may read.
The recorder and the history job collect the union of both, so a stock still
held keeps its price after it leaves the watchlist. Every read function here
takes the username and returns nothing for ISINs the user neither watches nor
holds.

Database: <API_DATA_DIR>/tradegate.db  (own file, like food.db)
  watchlist    which user follows which ISIN         PK (username, isin)
  trades       one row per Tradegate trade           PK (isin, date, trade_id)
  quotes       bid/ask snapshots (recorder --quotes) PK (isin, ts)
  daily        daily OHLCV bars for the Tradegate venue PK (isin, date)
  instruments  onvista lookup cache for the history job
  portfolio    a user's buys (+shares) and sells (-shares), one per row
  portfolio_settings  a user's tax rate on profits, in %
"""

import csv
import os
import re
import shutil
from datetime import date, timedelta

from api.config import API_DATA_DIR
from api.db import connect

TRADEGATE_DB = API_DATA_DIR / "tradegate.db"
TRADEGATE_DIR = API_DATA_DIR / "tradegate"

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    username TEXT NOT NULL,
    isin     TEXT NOT NULL,
    added    TEXT NOT NULL DEFAULT (datetime('now')),
    position INTEGER,                   -- the user's order; NULL (just added): last
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

CREATE TABLE IF NOT EXISTS portfolio (
    id       INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    isin     TEXT NOT NULL,
    date     TEXT NOT NULL,             -- YYYY-MM-DD of the transaction
    shares   REAL NOT NULL,             -- > 0 bought, < 0 sold
    price    REAL,                      -- per share; NULL: the day's close
    added    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS portfolio_user ON portfolio (username, isin);

CREATE TABLE IF NOT EXISTS portfolio_settings (
    username TEXT PRIMARY KEY,
    tax_rate REAL NOT NULL
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
            # Added after their tables: a database made before gets them here.
            if "price" not in {r[1] for r in conn.execute("PRAGMA table_info(portfolio)")}:
                conn.execute("ALTER TABLE portfolio ADD COLUMN price REAL")
            if "position" not in {r[1] for r in conn.execute("PRAGMA table_info(watchlist)")}:
                conn.execute("ALTER TABLE watchlist ADD COLUMN position INTEGER")
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
            "SELECT isin FROM watchlist WHERE username=? "
            "ORDER BY position IS NULL, position, added, isin", (user,))]


def watch(user, isins):
    with db() as conn:
        conn.executemany("INSERT OR IGNORE INTO watchlist (username, isin) VALUES (?,?)",
                         [(user, normalise_isin(i)) for i in isins])


def reorder(user, isins):
    """The user's list in this order; ISINs not on it are ignored."""
    with db() as conn:
        conn.executemany("UPDATE watchlist SET position=? WHERE username=? AND isin=?",
                         [(k, user, normalise_isin(i)) for k, i in enumerate(isins)])


def unwatch(user, isins):
    """Removes from the user's list only; the market data stays for others."""
    with db() as conn:
        conn.executemany("DELETE FROM watchlist WHERE username=? AND isin=?",
                         [(user, normalise_isin(i)) for i in isins])


def all_watched():
    """Every ISIN anyone watches or holds: what the recorder/history job collect."""
    with db() as conn:
        return [r[0] for r in conn.execute(
            "SELECT isin FROM watchlist UNION SELECT isin FROM portfolio ORDER BY isin")]


def followed():
    """user -> the ISINs they watch or hold: whose counters a stock's news moves."""
    with db() as conn:
        out: dict[str, set[str]] = {}
        for user, isin in conn.execute(
                "SELECT username, isin FROM watchlist UNION SELECT username, isin FROM portfolio"):
            out.setdefault(user, set()).add(isin)
        return out


def _may_read(conn, user, isin):
    return conn.execute("SELECT 1 FROM watchlist WHERE username=? AND isin=? "
                        "UNION ALL SELECT 1 FROM portfolio WHERE username=? AND isin=? LIMIT 1",
                        (user, isin, user, isin)).fetchone() is not None


# ----------------------------------------------------------------- portfolio

DEFAULT_TAX_RATE = 26.0


def transactions(user):
    """The user's transactions in the order they count: by date, a day's buys
    before its sells."""
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT p.id, p.isin, p.date, p.shares, p.price, COALESCE(i.name, p.isin) AS name "
            "FROM portfolio p LEFT JOIN instruments i ON i.isin = p.isin "
            "WHERE p.username=? ORDER BY p.date, p.shares < 0, p.id", (user,))]


def _never_short(rows):
    """Whether no sell in `rows` (counting order) sells more than is held."""
    held = {}
    for r in rows:
        held[r["isin"]] = held.get(r["isin"], 0.0) + r["shares"]
        if held[r["isin"]] < -1e-9:
            return False
    return True


def add_transaction(user, isin, day, shares, price=None):
    """Refused (ValueError) when a sell would leave fewer than 0 shares.
    `price` per share; None counts it at the day's close."""
    isin = normalise_isin(isin)
    rows = transactions(user) + [{"isin": isin, "date": day, "shares": shares, "id": 1 << 62}]
    rows.sort(key=lambda r: (r["date"], r["shares"] < 0, r["id"]))
    if not _never_short(rows):
        raise ValueError("more shares sold than held")
    with db() as conn:
        conn.execute("INSERT INTO portfolio (username, isin, date, shares, price) VALUES (?,?,?,?,?)",
                     (user, isin, day, shares, price))


def delete_transaction(user, tid):
    """Refused (ValueError) when a later sell would then sell more than is held.
    Returns whether there was such a transaction."""
    rows = transactions(user)
    rest = [r for r in rows if r["id"] != tid]
    if len(rest) == len(rows):
        return False
    if not _never_short(rest):
        raise ValueError("a later sale would sell more than is held")
    with db() as conn:
        conn.execute("DELETE FROM portfolio WHERE username=? AND id=?", (user, tid))
    return True


def tax_rate(user):
    with db() as conn:
        r = conn.execute("SELECT tax_rate FROM portfolio_settings WHERE username=?", (user,)).fetchone()
    return r[0] if r else DEFAULT_TAX_RATE


def set_tax_rate(user, rate):
    with db() as conn:
        conn.execute("INSERT INTO portfolio_settings (username, tax_rate) VALUES (?,?) "
                     "ON CONFLICT(username) DO UPDATE SET tax_rate=excluded.tax_rate", (user, rate))


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


def _today():
    return date.today().isoformat()


_csv_cache = {}   # path -> ((mtime_ns, size), rows): parse a file again only once it grew


def today_trades(isin, day=None):
    """The ticks the recorder has written today, from its CSV, in trade order:
    [(trade_id, time, price, size)]. The recorder appends while we read, so a
    half-written last line is skipped."""
    path = TRADEGATE_DIR / (day or _today()) / f"{isin}_trades.csv"
    try:
        st = path.stat()
    except FileNotFoundError:
        return []
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _csv_cache.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    out = []
    for r in _read_csv(path):
        try:
            price = _num(r["price"])
            if price is not None:
                out.append((int(r["trade_id"]), r["time"], price, _num(r["size"]) or 0.0))
        except (KeyError, TypeError, ValueError):
            pass
    out.sort()
    for old in [p for p in _csv_cache if p.parent != path.parent]:
        del _csv_cache[old]   # a past day's file
    _csv_cache[path] = (stamp, out)
    return out


def _bar(day, prices, sizes):
    return {"date": day, "open": prices[0], "high": max(prices), "low": min(prices),
            "close": prices[-1], "volume": sum(sizes), "trades": len(prices)}


def read_bars(user, isin, start=None, end=None):
    """Daily bars, merged from everything there is, newest source winning:
      1. `daily` (onvista's history),
      2. a finished day the recorder has in `trades` but the history job has
         not fetched yet, built from its ticks,
      3. today, built from the recorder's CSV -- its close is the last tick.
    Only for ISINs this user watches or holds."""
    start, end, today = start or "0000", end or "9999", _today()
    with db() as conn:
        if not _may_read(conn, user, isin):
            return []
        bars = {r["date"]: dict(r) for r in conn.execute(
            "SELECT date, open, high, low, close, volume, trades FROM daily "
            "WHERE isin=? AND date >= ? AND date <= ?", (isin, start, end))}
        for r in conn.execute(
                "SELECT date, MIN(price) AS low, MAX(price) AS high, SUM(size) AS volume, "
                "COUNT(*) AS trades, "
                "(SELECT price FROM trades f WHERE f.isin=t.isin AND f.date=t.date "
                " ORDER BY trade_id LIMIT 1) AS open, "
                "(SELECT price FROM trades l WHERE l.isin=t.isin AND l.date=t.date "
                " ORDER BY trade_id DESC LIMIT 1) AS close "
                "FROM trades t WHERE isin=? AND date >= ? AND date <= ? GROUP BY date",
                (isin, start, end)):
            if r["date"] not in bars:
                bars[r["date"]] = dict(r)
    if start <= today <= end:
        ticks = today_trades(isin, today)
        if ticks:
            bars[today] = _bar(today, [t[2] for t in ticks], [t[3] for t in ticks])
    return [bars[d] for d in sorted(bars)]


def read_ticks(user, isin, after=0):
    """Today's trades after trade id `after`, from the recorder's CSV, as
    [(trade_id, "YYYY-MM-DD HH:MM:SS.mmm", price, size)]. Only for ISINs on
    this user's watchlist. (Earlier days are daily bars: read_bars.)"""
    with db() as conn:
        if not _may_read(conn, user, isin):
            return []
    today = _today()
    return [(tid, f"{today} {t}", p, sz) for tid, t, p, sz in today_trades(isin, today) if tid > after]


def summaries(user):
    """The user's stocks, in the order added: name, history span, and the
    last two closes (today's last tick, if any, being the latest)."""
    out = []
    since = (date.today() - timedelta(days=14)).isoformat()
    for isin in watchlist(user):
        with db() as conn:
            name = conn.execute("SELECT name FROM instruments WHERE isin=?", (isin,)).fetchone()
            span = conn.execute("SELECT MIN(date), MAX(date) FROM daily WHERE isin=?",
                                (isin,)).fetchone()
        recent = read_bars(user, isin, since)
        out.append({
            "isin": isin,
            "name": name[0] if name and name[0] else isin,
            "min_date": span[0],
            "max_date": span[1],
            "last": recent[-1]["close"] if recent else None,
            "last_date": recent[-1]["date"] if recent else None,
            "prev_close": recent[-2]["close"] if len(recent) > 1 else None,
        })
    return out


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
