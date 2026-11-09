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
    bank, a wallet), "investment" too but in shares (the Stocks portfolio:
    its worth is the portfolio's, not what its payments add up to, and it
    stays out of the accounts' totals), "" is anything else (a spending, an
    income source). That alone tells a payment apart: into an account from
    elsewhere is income, out of one is spending, between two is a transfer.
  - finance_executed: what was actually paid — a self-contained snapshot
    (date, currency, justification) with its lines in finance_executed_lines.
    Nothing points into it and it points at nothing but categories: editing
    or deleting a row is all there is to moving or skipping a payment.
  - finance_forecasts: a payment template (its lines in
    finance_forecast_lines) plus a recurrence (the calendar's
    recur_freq / recur_interval / recur_until; no freq = a single date). The
    generator (run_forecasts) copies the template into finance_executed on
    every due date that has arrived and moves `generated_until` to it — its
    own bookmark, so running again never writes a date twice. It knows
    nothing of what happens to those rows afterwards. A forecast created with
    a start in the past writes every date already due at once.
  - finance_tags: the user's tags, each name once (letter case aside), on
    payments through finance_executed_tags and on forecasts through
    finance_forecast_tags (a forecast's are copied onto what it writes). A
    tag nothing carries any more is dropped.
  - fx_rates: the ECB's daily EUR -> USD reference rate (no weekends or
    holidays — rate_on() takes the latest one on or before a date), filled
    from 1999 the first time and day by day after that (update_fx).

A payment's lines say where its money came from and went to: each is a side
("from" / "to"), a category and an amount, and the two sides add up to the
same total — so one bill can be split over several categories on either side
(paid from two accounts, to light and gas). Which source paid which
destination isn't recorded, only each side's amounts. A line with no category
is outside the books: money coming in from nowhere (an opening balance, a
salary) or going out to nowhere. Amounts are whole cents."""
import json
import sqlite3
from datetime import datetime
import urllib.request
from contextlib import contextmanager
from datetime import date, timedelta

from api.config import FINANCE_DB, FX_URL
from api.db import bump, connect as _connect, get_version
from api.models import EventIn
from api.services import calendar as cal
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
    currency        TEXT NOT NULL,
    justification   TEXT NOT NULL DEFAULT '',
    start_date      TEXT NOT NULL,
    recur_freq      TEXT,
    recur_interval  INTEGER NOT NULL DEFAULT 1,
    recur_until     TEXT,
    -- the last due date already written to finance_executed (NULL: none yet)
    generated_until TEXT,
    -- its event in the Calendar (NULL: none), kept in step by _sync_event
    calendar_event_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fin_fc_user ON finance_forecasts(username);
CREATE TABLE IF NOT EXISTS finance_forecast_lines (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_id  INTEGER NOT NULL REFERENCES finance_forecasts(id) ON DELETE CASCADE,
    side         TEXT NOT NULL CHECK (side IN ('from', 'to')),
    category_id  INTEGER REFERENCES finance_categories(id),   -- NULL: outside
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0)
);
CREATE INDEX IF NOT EXISTS idx_fin_fc_lines ON finance_forecast_lines(forecast_id);
CREATE TABLE IF NOT EXISTS finance_executed (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    date          TEXT NOT NULL,
    currency      TEXT NOT NULL,
    justification TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fin_ex_user_date ON finance_executed(username, date);
CREATE TABLE IF NOT EXISTS finance_executed_lines (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_id  INTEGER NOT NULL REFERENCES finance_executed(id) ON DELETE CASCADE,
    side         TEXT NOT NULL CHECK (side IN ('from', 'to')),
    category_id  INTEGER REFERENCES finance_categories(id),   -- NULL: outside
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0)
);
CREATE INDEX IF NOT EXISTS idx_fin_ex_lines ON finance_executed_lines(executed_id);
CREATE TABLE IF NOT EXISTS finance_tags (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    name     TEXT NOT NULL COLLATE NOCASE,
    UNIQUE (username, name)
);
CREATE TABLE IF NOT EXISTS finance_executed_tags (
    executed_id INTEGER NOT NULL REFERENCES finance_executed(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES finance_tags(id),
    PRIMARY KEY (executed_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_fin_ex_tags_tag ON finance_executed_tags(tag_id);
CREATE TABLE IF NOT EXISTS finance_forecast_tags (
    forecast_id INTEGER NOT NULL REFERENCES finance_forecasts(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES finance_tags(id),
    PRIMARY KEY (forecast_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_fin_fc_tags_tag ON finance_forecast_tags(tag_id);
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
CATEGORY_KINDS = {"", "account", "investment"}
_PAYMENT_FIELDS = {"lines", "currency", "justification", "tags"}
# Each payment table's lines: (lines table, its column pointing at the payment).
_LINES = {"finance_executed": ("finance_executed_lines", "executed_id"),
          "finance_forecasts": ("finance_forecast_lines", "forecast_id")}
# ... and its tags: (link table, its column pointing at the payment).
_TAGS = {"finance_executed": ("finance_executed_tags", "executed_id"),
         "finance_forecasts": ("finance_forecast_tags", "forecast_id")}
_TAG_MAX = 100
_FORECAST_FIELDS = _PAYMENT_FIELDS | {"start_date", "recur_freq", "recur_interval", "recur_until", "calendar"}
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
        conn.commit()
        # Rebuilding a table is done with foreign keys off (dropping the old
        # one must not touch the lines pointing at its ids).
        conn.execute("PRAGMA foreign_keys = OFF")
        _migrate_lines(conn)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate(conn: sqlite3.Connection) -> None:
    """Columns added after a database already existed — CREATE TABLE IF NOT
    EXISTS in _SCHEMA only covers a brand-new one."""
    cat_cols = {r["name"] for r in conn.execute("PRAGMA table_info(finance_categories)")}
    if "kind" not in cat_cols:
        conn.execute("ALTER TABLE finance_categories ADD COLUMN kind TEXT NOT NULL DEFAULT ''")
    fc_cols = {r["name"] for r in conn.execute("PRAGMA table_info(finance_forecasts)")}
    if "calendar_event_id" not in fc_cols:
        conn.execute("ALTER TABLE finance_forecasts ADD COLUMN calendar_event_id INTEGER")


def _migrate_lines(conn: sqlite3.Connection) -> None:
    """Payments and forecasts from before lines (one from_id, one to_id, one
    amount each) become a header and two lines — a copy of the whole file
    is kept next to it first. The tables are rebuilt without the old
    columns, keeping their ids."""
    old = [t for t in _LINES
           if "from_id" in {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}]
    if not old:
        return
    backup = f"{FINANCE_DB}.before-lines-{datetime.now():%Y%m%d-%H%M%S}"
    with sqlite3.connect(backup) as dest:
        conn.backup(dest)
    header_cols = {
        "finance_executed": "id, username, date, currency, justification",
        "finance_forecasts": "id, username, currency, justification, start_date, recur_freq, "
                             "recur_interval, recur_until, generated_until",
    }
    for table in old:
        lines, key = _LINES[table]
        for side, col in (("from", "from_id"), ("to", "to_id")):
            conn.execute(f"INSERT INTO {lines}({key}, side, category_id, amount_cents) "
                         f"SELECT id, '{side}', {col}, amount_cents FROM {table} ORDER BY id")
        create = _SCHEMA[_SCHEMA.index(f"CREATE TABLE IF NOT EXISTS {table} ("):]
        create = create[:create.index(");") + 2].replace(f"IF NOT EXISTS {table}", f"{table}_new")
        conn.execute(create)
        cols = header_cols[table]
        conn.execute(f"INSERT INTO {table}_new({cols}) SELECT {cols} FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_fc_user ON finance_forecasts(username)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fin_ex_user_date ON finance_executed(username, date)")


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


# An icon is a set's name, or a small uploaded picture stored whole as a data: URL.
_ICON_MAX = 200_000


def _check_icon(icon) -> None:
    if not isinstance(icon, str) or len(icon) > _ICON_MAX:
        raise FinanceError("icon must be text of at most 200 KB")


def _check_kind(kind) -> None:
    if kind not in CATEGORY_KINDS:
        raise FinanceError(f"kind must be one of {sorted(CATEGORY_KINDS)}")


def _check_payment(conn: sqlite3.Connection, user: str, rec: dict) -> None:
    """Its lines: at least one a side, the two sides adding up to the same
    total, a category at most once a side and never on both, and not all of
    it outside the books."""
    if rec["currency"] not in CURRENCIES:
        raise FinanceError(f"currency must be one of {sorted(CURRENCIES)}")
    lines = rec["lines"]
    if not isinstance(lines, list):
        raise FinanceError("lines must be a list")
    sides: dict[str, list] = {"from": [], "to": []}
    totals = {"from": 0, "to": 0}
    for ln in lines:
        side, cat, cents = ln.get("side"), ln.get("category_id"), ln.get("amount_cents")
        if side not in sides:
            raise FinanceError("a line's side must be 'from' or 'to'")
        if not isinstance(cents, int) or isinstance(cents, bool) or cents <= 0:
            raise FinanceError("a line's amount_cents must be a positive whole number")
        if cat is not None:
            _own_category(conn, user, cat)
        if cat in sides[side]:
            raise FinanceError("a category can be on a side only once")
        sides[side].append(cat)
        totals[side] += cents
    if not sides["from"] or not sides["to"]:
        raise FinanceError("a payment needs at least one line on each side")
    if totals["from"] != totals["to"]:
        raise FinanceError("the from and to sides must add up to the same total")
    if set(sides["from"]) & set(sides["to"]):
        raise FinanceError("a category can't be on both sides")
    if all(c is None for c in sides["from"] + sides["to"]):
        raise FinanceError("a payment can't be all outside")


def _clean_tags(tags) -> list[str]:
    """Trimmed, the empty ones dropped, each once (letter case aside: the
    first spelling stays), in the order given."""
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise FinanceError("tags must be a list of text")
    out: list[str] = []
    for t in (t.strip() for t in tags):
        if len(t) > _TAG_MAX:
            raise FinanceError(f"a tag can be at most {_TAG_MAX} characters")
        if t and t.casefold() not in {o.casefold() for o in out}:
            out.append(t)
    return out


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
    if table not in _LINES:
        return dict(row)
    return _with_lines(conn, table, [dict(row)])[0]


def _with_lines(conn: sqlite3.Connection, table: str, rows: list[dict]) -> list[dict]:
    """Each payment (or forecast) of `rows` with its `lines`, from-side
    first, and its `tags` (names, in the order they were given)."""
    lines, key = _LINES[table]
    links, tkey = _TAGS[table]
    by_id: dict[int, list] = {r["id"]: [] for r in rows}
    tags: dict[int, list] = {r["id"]: [] for r in rows}
    if by_id:
        marks = ", ".join("?" * len(by_id))
        for ln in conn.execute(
            f"SELECT {key} AS pid, side, category_id, amount_cents FROM {lines} "
            f"WHERE {key} IN ({marks}) ORDER BY side, id", tuple(by_id),
        ):
            by_id[ln["pid"]].append({"side": ln["side"], "category_id": ln["category_id"],
                                     "amount_cents": ln["amount_cents"]})
        for tg in conn.execute(
            f"SELECT l.{tkey} AS pid, t.name FROM {links} l JOIN finance_tags t ON t.id = l.tag_id "
            f"WHERE l.{tkey} IN ({marks}) ORDER BY l.rowid", tuple(by_id),
        ):
            tags[tg["pid"]].append(tg["name"])
    return [{**r, "lines": by_id[r["id"]], "tags": tags[r["id"]]} for r in rows]


def _write_tags(conn: sqlite3.Connection, table: str, user: str, row_id: int, names: list[str]) -> None:
    """Replace a payment's (or forecast's) tags with `names` (already
    cleaned): a name the user has never used becomes a new tag, one already
    there (letter case aside) is reused as it was first spelt."""
    links, key = _TAGS[table]
    conn.execute(f"DELETE FROM {links} WHERE {key} = ?", (row_id,))
    for name in names:
        conn.execute("INSERT OR IGNORE INTO finance_tags(username, name) VALUES(?, ?)", (user, name))
        tag_id = conn.execute("SELECT id FROM finance_tags WHERE username = ? AND name = ?",
                              (user, name)).fetchone()[0]
        conn.execute(f"INSERT OR IGNORE INTO {links}({key}, tag_id) VALUES(?, ?)", (row_id, tag_id))
    _prune_tags(conn, user)


def _prune_tags(conn: sqlite3.Connection, user: str) -> None:
    """A tag no payment or forecast carries any more goes."""
    conn.execute(
        "DELETE FROM finance_tags WHERE username = ? "
        "AND id NOT IN (SELECT tag_id FROM finance_executed_tags) "
        "AND id NOT IN (SELECT tag_id FROM finance_forecast_tags)", (user,),
    )


def _write_lines(conn: sqlite3.Connection, table: str, row_id: int, lines: list[dict]) -> None:
    """Replace a payment's (or forecast's) lines with `lines`."""
    lt, key = _LINES[table]
    conn.execute(f"DELETE FROM {lt} WHERE {key} = ?", (row_id,))
    conn.executemany(
        f"INSERT INTO {lt}({key}, side, category_id, amount_cents) VALUES(?, ?, ?, ?)",
        [(row_id, ln["side"], ln.get("category_id"), ln["amount_cents"]) for ln in lines],
    )


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
    _check_icon(rec["icon"])
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
    if "icon" in fields:
        _check_icon(fields["icon"])
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
        "OR EXISTS(SELECT 1 FROM finance_executed_lines WHERE category_id = :id) "
        "OR EXISTS(SELECT 1 FROM finance_forecast_lines WHERE category_id = :id)",
        {"id": cat_id},
    ).fetchone()[0]
    if used:
        raise FinanceError("category is in use — archive it instead", 409)
    conn.execute("DELETE FROM finance_categories WHERE id = ?", (cat_id,))
    bump(conn, version_key(user))


# ── executed payments ──────────────────────────────────────────────────────
def list_executed(conn: sqlite3.Connection, user: str) -> list[dict]:
    """Every payment with its lines, newest first."""
    rows = conn.execute(
        "SELECT * FROM finance_executed WHERE username = ? ORDER BY date DESC, id DESC", (user,),
    ).fetchall()
    return _with_lines(conn, "finance_executed", [dict(r) for r in rows])


def _header(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k not in ("id", "username", "lines", "tags", "calendar")}


def create_executed(conn: sqlite3.Connection, user: str, fields: dict) -> dict:
    _unknown(fields, _EXECUTED_FIELDS)
    rec = {"justification": "", **fields}
    for key in ("date", "lines", "currency"):
        if key not in rec:
            raise FinanceError(f"{key} is required")
    _iso(rec["date"], "date")
    _check_payment(conn, user, rec)
    tags = _clean_tags(rec.get("tags", []))
    new_id = _insert(conn, "finance_executed", user, _header(rec))
    _write_lines(conn, "finance_executed", new_id, rec["lines"])
    _write_tags(conn, "finance_executed", user, new_id, tags)
    bump(conn, version_key(user))
    return _get(conn, "finance_executed", user, new_id)


def update_executed(conn: sqlite3.Connection, user: str, row_id: int, fields: dict) -> dict:
    """`lines`, when given, replace all of the payment's lines."""
    _unknown(fields, _EXECUTED_FIELDS)
    rec = {**_get(conn, "finance_executed", user, row_id), **fields}
    _iso(rec["date"], "date")
    _check_payment(conn, user, rec)
    _update(conn, "finance_executed", row_id, _header(fields))
    if "lines" in fields:
        _write_lines(conn, "finance_executed", row_id, fields["lines"])
    if "tags" in fields:
        _write_tags(conn, "finance_executed", user, row_id, _clean_tags(fields["tags"]))
    bump(conn, version_key(user))
    return _get(conn, "finance_executed", user, row_id)


def delete_executed(conn: sqlite3.Connection, user: str, row_id: int) -> None:
    _get(conn, "finance_executed", user, row_id)
    conn.execute("DELETE FROM finance_executed WHERE id = ?", (row_id,))
    _prune_tags(conn, user)
    bump(conn, version_key(user))


# ── forecasts ──────────────────────────────────────────────────────────────
def list_forecasts(conn: sqlite3.Connection, user: str) -> list[dict]:
    """Each with its `calendar`: its event's calendar and alarm, or None —
    none, or deleted from the Calendar since."""
    rows = conn.execute(
        "SELECT * FROM finance_forecasts WHERE username = ? ORDER BY start_date, id", (user,),
    ).fetchall()
    ids = [r["calendar_event_id"] for r in rows if r["calendar_event_id"] is not None]
    events = {}
    if ids:
        with cal.connect() as cconn:
            events = cal.event_settings(cconn, user, ids)
    return [{**f, "calendar": events.get(f["calendar_event_id"])}
            for f in _with_lines(conn, "finance_forecasts", [dict(r) for r in rows])]


def calendar_open(user: str) -> bool:
    """Whether `user` has the Calendar, so a forecast of theirs may have an event there."""
    from api.auth import visible_panels
    vis = visible_panels(user)
    return vis is None or "calendar" in vis


def _sync_event(conn: sqlite3.Connection, user: str, row_id: int, link: dict | None) -> None:
    """Keep forecast `row_id`'s event in the Calendar in step with it: `link`
    ({calendar_id, alarm, alarm_lead, time}) makes or rewrites it — the same
    dates and repetition, titled by its reason (else From → To), its amount
    as description, unless `link` brings its own `title` and `description`
    (the client's, in its language) — at `time` when it has an alarm (all
    day otherwise); None removes it."""
    f = _get(conn, "finance_forecasts", user, row_id)
    event_id = f["calendar_event_id"]
    if link is not None and not calendar_open(user):
        raise FinanceError("the Calendar isn't open to you", 403)
    try:
        with cal.connect() as cconn:
            if link is None:
                if event_id is not None:
                    cal.drop_event(cconn, user, event_id)
                new_id = None
            else:
                names = {c["id"]: c["name"] for c in list_categories(conn, user)}
                side = lambda s: ", ".join(names.get(ln["category_id"], "") for ln in f["lines"]
                                           if ln["side"] == s and ln["category_id"] is not None)
                title = f["justification"].strip() or f"{side('from') or '…'} → {side('to') or '…'}"
                total = sum(ln["amount_cents"] for ln in f["lines"] if ln["side"] == "from")
                timed = bool(link.get("alarm") and link.get("time"))
                if timed:
                    h, m = map(int, link["time"].split(":"))
                    end = min(h * 60 + m + 30, 23 * 60 + 59)
                    if end <= h * 60 + m:
                        raise FinanceError("the alarm's time must be before 23:59")
                new_id = cal.put_event(cconn, user, event_id, EventIn(
                    title=link.get("title") or title,
                    description=link.get("description") or f"{total / 100:.2f} {f['currency']}",
                    start_date=f["start_date"], end_date=f["start_date"], all_day=not timed,
                    start_time=link["time"] if timed else None,
                    end_time=f"{end // 60:02d}:{end % 60:02d}" if timed else None,
                    calendar_id=link["calendar_id"], recur_freq=f["recur_freq"],
                    recur_interval=f["recur_interval"], recur_until=f["recur_until"],
                    alarm=bool(link.get("alarm")), alarm_lead=link.get("alarm_lead") or 0,
                ))
    except cal.CalendarError as e:
        raise FinanceError(str(e), e.status_code)
    if new_id != event_id:
        _update(conn, "finance_forecasts", row_id, {"calendar_event_id": new_id})


def create_forecast(conn: sqlite3.Connection, user: str, fields: dict) -> dict:
    _unknown(fields, _FORECAST_FIELDS)
    rec = {"justification": "", "recur_freq": None, "recur_interval": 1, "recur_until": None, **fields}
    for key in ("start_date", "lines", "currency"):
        if key not in rec:
            raise FinanceError(f"{key} is required")
    _check_payment(conn, user, rec)
    _check_recurrence(rec)
    tags = _clean_tags(rec.get("tags", []))
    new_id = _insert(conn, "finance_forecasts", user, _header(rec))
    _write_lines(conn, "finance_forecasts", new_id, rec["lines"])
    _write_tags(conn, "finance_forecasts", user, new_id, tags)
    if rec.get("calendar"):
        _sync_event(conn, user, new_id, rec["calendar"])
    bump(conn, version_key(user))
    run_forecasts(conn, user=user)   # a date already due shows up now, not tomorrow
    return _get(conn, "finance_forecasts", user, new_id)


def update_forecast(conn: sqlite3.Connection, user: str, row_id: int, fields: dict) -> dict:
    """Changes what future dates write; rows already written stay as they are.
    `lines`, when given, replace all of the forecast's lines. `calendar`,
    when given, links it to an event in the Calendar or (None) unlinks it;
    a linked one's event follows every change."""
    _unknown(fields, _FORECAST_FIELDS)
    old = _get(conn, "finance_forecasts", user, row_id)
    rec = {**old, **fields}
    _check_payment(conn, user, rec)
    _check_recurrence(rec)
    _update(conn, "finance_forecasts", row_id, _header(fields))
    if "lines" in fields:
        _write_lines(conn, "finance_forecasts", row_id, fields["lines"])
    if "tags" in fields:
        _write_tags(conn, "finance_forecasts", user, row_id, _clean_tags(fields["tags"]))
    if "calendar" in fields:
        _sync_event(conn, user, row_id, fields["calendar"])
    elif old["calendar_event_id"] is not None and calendar_open(user):
        # Still linked: the event takes the new dates, title and amount, its
        # calendar and alarm as they are now.
        with cal.connect() as cconn:
            link = cal.event_settings(cconn, user, [old["calendar_event_id"]]).get(old["calendar_event_id"])
        if link:
            _sync_event(conn, user, row_id, link)
    bump(conn, version_key(user))
    run_forecasts(conn, user=user)
    return _get(conn, "finance_forecasts", user, row_id)


def delete_forecast(conn: sqlite3.Connection, user: str, row_id: int) -> None:
    """Stops future dates; rows already written stay. Its event in the
    Calendar goes with it."""
    _sync_event(conn, user, row_id, None)
    conn.execute("DELETE FROM finance_forecasts WHERE id = ?", (row_id,))
    _prune_tags(conn, user)
    bump(conn, version_key(user))


def _due_dates(f: dict, after: date, through: date):
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
    for f in _with_lines(conn, "finance_forecasts", [dict(r) for r in conn.execute(sql, args)]):
        after = (date.fromisoformat(f["generated_until"]) + timedelta(days=1)
                 if f["generated_until"] else date.min)
        last = None
        for d in _due_dates(f, after, today):
            new_id = _insert(conn, "finance_executed", f["username"], {
                "date": d.isoformat(), "currency": f["currency"], "justification": f["justification"],
            })
            _write_lines(conn, "finance_executed", new_id, f["lines"])
            _write_tags(conn, "finance_executed", f["username"], new_id, f["tags"])
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


def rates_since(conn: sqlite3.Connection, day: str) -> list[list]:
    """Every EUR -> USD rate from the one in force on `day` (the latest on or
    before it) to the newest, oldest first, as [date, rate] pairs."""
    start = conn.execute(
        "SELECT MAX(date) FROM fx_rates WHERE base = ? AND quote = ? AND date <= ?", (*_FX_PAIR, day),
    ).fetchone()[0] or day
    return [[r["date"], r["rate"]] for r in conn.execute(
        "SELECT date, rate FROM fx_rates WHERE base = ? AND quote = ? AND date >= ? ORDER BY date",
        (*_FX_PAIR, start),
    )]


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
