"""Finance service storage — a self-contained module (own SQLite file, own
per-user `"<user>:finance_version"` counter), following calendar.py's
template. Every row is owned by a `username` and every query filters on it.

Three tables per user, plus one shared:
  - finance_categories: one table for categories and sub-categories alike —
    a sub-category is just a row with a `parent_id`, so the UI can stack any
    category under any other (or pull it back out) by changing that one
    column. `sort` is the order among siblings. A category that has been used
    is archived rather than deleted, so old payments keep their names.
    `kind` says what a category is: "account" holds the user's own money (a
    bank, a wallet), "" is anything else (a spending, an income source).
    That alone tells a payment apart: into an account from elsewhere is
    income, out of one is spending, between two is a transfer.
  - finance_executed: what was actually paid — a self-contained snapshot
    (date, from, to, amount, currency, justification). Nothing points into
    it and it points at nothing but categories: editing or deleting a row is
    all there is to moving or skipping a payment.
  - finance_forecasts: a payment template plus a recurrence (the calendar's
    recur_freq / recur_interval / recur_until; no freq = a single date). The
    generator (run_forecasts) copies the template into finance_executed on
    every due date that has arrived and moves `generated_until` to it — its
    own bookmark, so running again never writes a date twice. It knows
    nothing of what happens to those rows afterwards. A forecast created with
    a start in the past writes every date already due at once.
  - fx_rates: the ECB's daily EUR -> USD reference rate (no weekends or
    holidays — rate_on() takes the latest one on or before a date), filled
    from 1999 the first time and day by day after that (update_fx).

`from_id` / `to_id` empty means outside the books: money coming in from
nowhere (an opening balance, a salary) or going out to nowhere. They can't
both be empty. Amounts are whole cents."""
import json
import sqlite3
import urllib.request
from contextlib import contextmanager
from datetime import date, timedelta

from api.config import FINANCE_DB, FX_URL
from api.db import bump, connect as _connect, get_version
from api.services.calendar import _add_months

_SCHEMA = """
CREATE TABLE IF NOT EXISTS finance_categories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT NOT NULL,
    parent_id INTEGER REFERENCES finance_categories(id),
    name      TEXT NOT NULL,
    icon      TEXT NOT NULL DEFAULT '',
    sort      INTEGER NOT NULL DEFAULT 0,
    archived  INTEGER NOT NULL DEFAULT 0,
    kind      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fin_cat_user ON finance_categories(username);
CREATE TABLE IF NOT EXISTS finance_forecasts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL,
    from_id         INTEGER REFERENCES finance_categories(id),
    to_id           INTEGER REFERENCES finance_categories(id),
    amount_cents    INTEGER NOT NULL,
    currency        TEXT NOT NULL,
    justification   TEXT NOT NULL DEFAULT '',
    start_date      TEXT NOT NULL,
    recur_freq      TEXT,
    recur_interval  INTEGER NOT NULL DEFAULT 1,
    recur_until     TEXT,
    -- the last due date already written to finance_executed (NULL: none yet)
    generated_until TEXT
);
CREATE INDEX IF NOT EXISTS idx_fin_fc_user ON finance_forecasts(username);
CREATE TABLE IF NOT EXISTS finance_executed (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    date          TEXT NOT NULL,
    from_id       INTEGER REFERENCES finance_categories(id),
    to_id         INTEGER REFERENCES finance_categories(id),
    amount_cents  INTEGER NOT NULL,
    currency      TEXT NOT NULL,
    justification TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fin_ex_user_date ON finance_executed(username, date);
CREATE TABLE IF NOT EXISTS fx_rates (
    date  TEXT NOT NULL,
    base  TEXT NOT NULL,
    quote TEXT NOT NULL,
    rate  REAL NOT NULL,
    PRIMARY KEY (base, quote, date)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

CURRENCIES = {"EUR", "USD"}
_RECUR_FREQS = {"daily", "weekly", "monthly", "yearly"}
_FX_PAIR = ("EUR", "USD")
_FX_FIRST_DAY = date(1999, 1, 4)   # the ECB's first published rate

_CATEGORY_FIELDS = {"parent_id", "name", "icon", "sort", "archived", "kind"}
CATEGORY_KINDS = {"", "account"}
_PAYMENT_FIELDS = {"from_id", "to_id", "amount_cents", "currency", "justification"}
_FORECAST_FIELDS = _PAYMENT_FIELDS | {"start_date", "recur_freq", "recur_interval", "recur_until"}
_EXECUTED_FIELDS = _PAYMENT_FIELDS | {"date"}


class FinanceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@contextmanager
def connect():
    with _connect(FINANCE_DB) as conn:
        yield conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Columns added after a database already existed — CREATE TABLE IF NOT
    EXISTS in _SCHEMA only covers a brand-new one."""
    cat_cols = {r["name"] for r in conn.execute("PRAGMA table_info(finance_categories)")}
    if "kind" not in cat_cols:
        conn.execute("ALTER TABLE finance_categories ADD COLUMN kind TEXT NOT NULL DEFAULT ''")


def version_key(user: str) -> str:
    return f"{user}:finance_version"


def version(conn: sqlite3.Connection, user: str) -> int:
    return get_version(conn, version_key(user))


# ── validation ─────────────────────────────────────────────────────────────
def _iso(value: str, what: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise FinanceError(f"{what} must be a YYYY-MM-DD date")


def _own_category(conn: sqlite3.Connection, user: str, cat_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM finance_categories WHERE id = ? AND username = ?", (cat_id, user),
    ).fetchone()
    if row is None:
        raise FinanceError(f"category {cat_id} not found", 404)
    return row


def _check_parent(conn: sqlite3.Connection, user: str, cat_id: int | None, parent_id: int | None) -> None:
    """The parent must be the user's, and stacking must not make a loop
    (a category under itself or under one of its own descendants)."""
    p = parent_id
    while p is not None:
        if p == cat_id:
            raise FinanceError("a category can't sit under itself or its own sub-categories")
        p = _own_category(conn, user, p)["parent_id"]


def _check_kind(kind) -> None:
    if kind not in CATEGORY_KINDS:
        raise FinanceError(f"kind must be one of {sorted(CATEGORY_KINDS)}")


def _check_payment(conn: sqlite3.Connection, user: str, rec: dict) -> None:
    if rec["from_id"] is None and rec["to_id"] is None:
        raise FinanceError("from and to can't both be empty")
    if rec["from_id"] == rec["to_id"]:
        raise FinanceError("from and to must differ")
    for key in ("from_id", "to_id"):
        if rec[key] is not None:
            _own_category(conn, user, rec[key])
    if not isinstance(rec["amount_cents"], int) or rec["amount_cents"] <= 0:
        raise FinanceError("amount_cents must be a positive whole number")
    if rec["currency"] not in CURRENCIES:
        raise FinanceError(f"currency must be one of {sorted(CURRENCIES)}")


def _check_recurrence(rec: dict) -> None:
    start = _iso(rec["start_date"], "start_date")
    if rec["recur_freq"] is None:
        return
    if rec["recur_freq"] not in _RECUR_FREQS:
        raise FinanceError(f"invalid recur_freq {rec['recur_freq']!r}")
    if not isinstance(rec["recur_interval"], int) or rec["recur_interval"] < 1:
        raise FinanceError("recur_interval must be at least 1")
    if rec["recur_until"] is not None and _iso(rec["recur_until"], "recur_until") < start:
        raise FinanceError("recur_until must not be before start_date")


def _unknown(fields: dict, allowed: set[str]) -> None:
    extra = set(fields) - allowed
    if extra:
        raise FinanceError(f"unknown fields: {sorted(extra)}")


def _get(conn: sqlite3.Connection, table: str, user: str, row_id: int) -> dict:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ? AND username = ?", (row_id, user)).fetchone()
    if row is None:
        raise FinanceError(f"{row_id} not found", 404)
    return dict(row)


def _insert(conn: sqlite3.Connection, table: str, user: str, rec: dict) -> int:
    cols = ["username", *rec]
    return conn.execute(
        f"INSERT INTO {table}({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
        (user, *rec.values()),
    ).lastrowid


def _update(conn: sqlite3.Connection, table: str, row_id: int, fields: dict) -> None:
    if fields:
        conn.execute(
            f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
            (*fields.values(), row_id),
        )


# ── categories ─────────────────────────────────────────────────────────────
def list_categories(conn: sqlite3.Connection, user: str) -> list[dict]:
    """Flat, in display order; the tree is rebuilt from parent_id."""
    rows = conn.execute(
        "SELECT * FROM finance_categories WHERE username = ? ORDER BY sort, id", (user,),
    ).fetchall()
    return [{**dict(r), "archived": bool(r["archived"])} for r in rows]


def create_category(conn: sqlite3.Connection, user: str, fields: dict) -> dict:
    _unknown(fields, _CATEGORY_FIELDS)
    rec = {"parent_id": None, "icon": "", "archived": False, **fields}
    if not str(rec.get("name") or "").strip():
        raise FinanceError("name is required")
    rec["name"] = rec["name"].strip()
    rec["archived"] = int(bool(rec["archived"]))
    _check_kind(rec.get("kind", ""))
    _check_parent(conn, user, None, rec["parent_id"])
    rec.setdefault("sort", _next_sort(conn, user, rec["parent_id"]))
    new_id = _insert(conn, "finance_categories", user, rec)
    bump(conn, version_key(user))
    return _get(conn, "finance_categories", user, new_id)


def update_category(conn: sqlite3.Connection, user: str, cat_id: int, fields: dict) -> dict:
    _unknown(fields, _CATEGORY_FIELDS)
    _own_category(conn, user, cat_id)
    if "name" in fields:
        if not str(fields["name"] or "").strip():
            raise FinanceError("name is required")
        fields["name"] = fields["name"].strip()
    if "parent_id" in fields:
        _check_parent(conn, user, cat_id, fields["parent_id"])
        if "sort" not in fields and fields["parent_id"] != _own_category(conn, user, cat_id)["parent_id"]:
            fields["sort"] = _next_sort(conn, user, fields["parent_id"])
    if "archived" in fields:
        fields["archived"] = int(bool(fields["archived"]))
    if "kind" in fields:
        _check_kind(fields["kind"])
    _update(conn, "finance_categories", cat_id, fields)
    bump(conn, version_key(user))
    return _get(conn, "finance_categories", user, cat_id)


def _next_sort(conn: sqlite3.Connection, user: str, parent_id: int | None) -> int:
    """After the last of parent_id's sub-categories (a new or moved one goes last)."""
    row = conn.execute(
        "SELECT MAX(sort) FROM finance_categories WHERE username = ? AND parent_id IS ?", (user, parent_id),
    ).fetchone()
    return 0 if row[0] is None else row[0] + 1


def move_categories(conn: sqlite3.Connection, user: str, parent_id: int | None, ids: list[int]) -> None:
    """parent_id's sub-categories in their new order (dragged in the list):
    each moves under parent_id, if it wasn't there, and gets its index as sort."""
    if len(set(ids)) != len(ids):
        raise FinanceError("ids must not repeat")
    for n, i in enumerate(ids):
        _own_category(conn, user, i)
        _check_parent(conn, user, i, parent_id)
        _update(conn, "finance_categories", i, {"parent_id": parent_id, "sort": n})
    bump(conn, version_key(user))


def delete_category(conn: sqlite3.Connection, user: str, cat_id: int) -> None:
    """Only a category nothing refers to — no sub-categories, no payments, no
    forecasts. Anything else is archived instead, so history keeps its name."""
    _own_category(conn, user, cat_id)
    used = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM finance_categories WHERE parent_id = :id) "
        "OR EXISTS(SELECT 1 FROM finance_executed WHERE from_id = :id OR to_id = :id) "
        "OR EXISTS(SELECT 1 FROM finance_forecasts WHERE from_id = :id OR to_id = :id)",
        {"id": cat_id},
    ).fetchone()[0]
    if used:
        raise FinanceError("category is in use — archive it instead", 409)
    conn.execute("DELETE FROM finance_categories WHERE id = ?", (cat_id,))
    bump(conn, version_key(user))


# ── executed payments ──────────────────────────────────────────────────────
def list_executed(conn: sqlite3.Connection, user: str) -> list[dict]:
    """Every payment, newest first."""
    rows = conn.execute(
        "SELECT * FROM finance_executed WHERE username = ? ORDER BY date DESC, id DESC", (user,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_executed(conn: sqlite3.Connection, user: str, fields: dict) -> dict:
    _unknown(fields, _EXECUTED_FIELDS)
    rec = {"from_id": None, "to_id": None, "justification": "", **fields}
    for key in ("date", "amount_cents", "currency"):
        if key not in rec:
            raise FinanceError(f"{key} is required")
    _iso(rec["date"], "date")
    _check_payment(conn, user, rec)
    new_id = _insert(conn, "finance_executed", user, rec)
    bump(conn, version_key(user))
    return _get(conn, "finance_executed", user, new_id)


def update_executed(conn: sqlite3.Connection, user: str, row_id: int, fields: dict) -> dict:
    _unknown(fields, _EXECUTED_FIELDS)
    rec = {**_get(conn, "finance_executed", user, row_id), **fields}
    _iso(rec["date"], "date")
    _check_payment(conn, user, rec)
    _update(conn, "finance_executed", row_id, fields)
    bump(conn, version_key(user))
    return _get(conn, "finance_executed", user, row_id)


def delete_executed(conn: sqlite3.Connection, user: str, row_id: int) -> None:
    _get(conn, "finance_executed", user, row_id)
    conn.execute("DELETE FROM finance_executed WHERE id = ?", (row_id,))
    bump(conn, version_key(user))


# ── forecasts ──────────────────────────────────────────────────────────────
def list_forecasts(conn: sqlite3.Connection, user: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM finance_forecasts WHERE username = ? ORDER BY start_date, id", (user,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_forecast(conn: sqlite3.Connection, user: str, fields: dict) -> dict:
    _unknown(fields, _FORECAST_FIELDS)
    rec = {"from_id": None, "to_id": None, "justification": "",
           "recur_freq": None, "recur_interval": 1, "recur_until": None, **fields}
    for key in ("start_date", "amount_cents", "currency"):
        if key not in rec:
            raise FinanceError(f"{key} is required")
    _check_payment(conn, user, rec)
    _check_recurrence(rec)
    new_id = _insert(conn, "finance_forecasts", user, rec)
    bump(conn, version_key(user))
    run_forecasts(conn, user=user)   # a date already due shows up now, not tomorrow
    return _get(conn, "finance_forecasts", user, new_id)


def update_forecast(conn: sqlite3.Connection, user: str, row_id: int, fields: dict) -> dict:
    """Changes what future dates write; rows already written stay as they are."""
    _unknown(fields, _FORECAST_FIELDS)
    rec = {**_get(conn, "finance_forecasts", user, row_id), **fields}
    _check_payment(conn, user, rec)
    _check_recurrence(rec)
    _update(conn, "finance_forecasts", row_id, fields)
    bump(conn, version_key(user))
    run_forecasts(conn, user=user)
    return _get(conn, "finance_forecasts", user, row_id)


def delete_forecast(conn: sqlite3.Connection, user: str, row_id: int) -> None:
    """Stops future dates; rows already written stay."""
    _get(conn, "finance_forecasts", user, row_id)
    conn.execute("DELETE FROM finance_forecasts WHERE id = ?", (row_id,))
    bump(conn, version_key(user))


def _due_dates(f: sqlite3.Row, after: date, through: date):
    """Due dates of one forecast in [after, through], each computed from the
    start (not from the previous one), so a monthly on the 31st comes back to
    the 31st after a short month."""
    start = date.fromisoformat(f["start_date"])
    until = date.fromisoformat(f["recur_until"]) if f["recur_until"] else None
    freq, n = f["recur_freq"], f["recur_interval"]
    k = 0
    while True:
        if freq is None:
            d = start
        elif freq in ("daily", "weekly"):
            d = start + timedelta(days=k * n * (1 if freq == "daily" else 7))
        else:
            d = _add_months(start, k * n * (1 if freq == "monthly" else 12))
        if d > through or (until and d > until):
            return
        if d >= after:
            yield d
        if freq is None:
            return
        k += 1


def run_forecasts(conn: sqlite3.Connection, today: date | None = None, user: str | None = None) -> set[str]:
    """Write every due date that has arrived (up to and including today) and
    hasn't been written yet. Returns the users who got new payments."""
    today = today or date.today()
    sql, args = "SELECT * FROM finance_forecasts", ()
    if user is not None:
        sql, args = sql + " WHERE username = ?", (user,)
    touched: set[str] = set()
    for f in conn.execute(sql, args).fetchall():
        after = (date.fromisoformat(f["generated_until"]) + timedelta(days=1)
                 if f["generated_until"] else date.min)
        last = None
        for d in _due_dates(f, after, today):
            _insert(conn, "finance_executed", f["username"], {
                "date": d.isoformat(), "from_id": f["from_id"], "to_id": f["to_id"],
                "amount_cents": f["amount_cents"], "currency": f["currency"],
                "justification": f["justification"],
            })
            last = d
        if last is not None:
            conn.execute("UPDATE finance_forecasts SET generated_until = ? WHERE id = ?",
                         (last.isoformat(), f["id"]))
            touched.add(f["username"])
    for u in touched:
        bump(conn, version_key(u))
    return touched


# ── exchange rates ─────────────────────────────────────────────────────────
def _fetch_rates(start: date, end: date) -> dict[str, float]:
    base, quote = _FX_PAIR
    url = f"{FX_URL}/{start.isoformat()}..{end.isoformat()}?base={base}&symbols={quote}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    # A range starting on a weekend or holiday comes back with the business
    # day before it too: keep only what was asked for.
    return {d: r[quote] for d, r in data.get("rates", {}).items()
            if quote in r and d >= start.isoformat()}


def update_fx(today: date | None = None) -> int:
    """Fetch every day after the newest stored rate (from 1999 on an empty
    table), a year per request. Returns how many rates were added."""
    today = today or date.today()
    base, quote = _FX_PAIR
    with connect() as conn:
        newest = conn.execute(
            "SELECT MAX(date) FROM fx_rates WHERE base = ? AND quote = ?", (base, quote),
        ).fetchone()[0]
    start = date.fromisoformat(newest) + timedelta(days=1) if newest else _FX_FIRST_DAY
    added = 0
    while start <= today:
        end = min(date(start.year, 12, 31), today)
        rates = _fetch_rates(start, end)
        with connect() as conn:   # commit year by year: a failure keeps what came in
            conn.executemany(
                "INSERT OR IGNORE INTO fx_rates(date, base, quote, rate) VALUES(?, ?, ?, ?)",
                [(d, base, quote, r) for d, r in rates.items()],
            )
        added += len(rates)
        start = end + timedelta(days=1)
    return added


def rate_on(conn: sqlite3.Connection, day: str, base: str = "EUR", quote: str = "USD") -> float | None:
    """How many `quote` one `base` buys on `day`: that day's rate, or the
    latest before it (weekends and holidays have none). Either direction."""
    if base == quote:
        return 1.0
    flip = (base, quote) != _FX_PAIR
    a, b = (quote, base) if flip else (base, quote)
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE base = ? AND quote = ? AND date <= ? ORDER BY date DESC LIMIT 1",
        (a, b, day),
    ).fetchone()
    if row is None:
        return None
    return 1 / row[0] if flip else row[0]
