"""Calendar service storage — a self-contained module (own SQLite file, own
version counter), mirroring food.py's template. No external account: every
event lives only in this DB.

Every event belongs to exactly one calendar (`calendar_id`), and every
calendar has an owner — whoever made it; every user gets a "Default" one
lazily the first time they need it, and can make more (`create_calendar`).
A calendar is private to its owner until the owner shares it, the same way
an album of the Images library is shared (api/services/image_access.py):
`people` names who else sees it and what they may do there —
  - "see":    its events show in their calendar, read-only (they may still
              acknowledge or snooze an event's alarm);
  - "edit":   they may also add, change and delete its events;
  - "manage": they may also rename and recolour it and change who it is
              shared with.
Only the owner deletes it. There is no admin over calendars: nobody sees a
calendar that was not shared with them. `shared` is kept as a column only as
"people is not empty", for the clients that show it.

Every event has a start_date/end_date span (end_date == start_date for a
plain single-day event) plus an `all_day` flag; when all_day is false,
start_time/end_time apply on top of that span. `all_day` only ever toggles
whether the time-of-day portion is used — it never implies single-day, so a
multi-day all-day event (e.g. a long weekend) is just start_date < end_date
with all_day=True.

Recurrence (recur_freq/recur_interval/recur_until) is stored once on the
event's own row — there is no row per occurrence. list_month() expands a
recurring event's occurrences that overlap the requested month on every read
("recomputed by the backend"), each carrying the same `id` as the master row.
Editing always acts on the whole series (there's no per-occurrence "change
just this one"). Deleting can go either way: delete_event's `occurrence`
parameter, when given, adds that one date to the row's `recur_exceptions`
list instead of removing the row — "delete this event" for a single
occurrence vs. "delete series" for the whole thing.

A single global `calendar_version` counter covers both kinds (like
weather_version) rather than a per-user one: a shared event changing is
relevant to everyone anyway, and the extra precision of scoping personal-only
changes to just their owner isn't worth the complexity here."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from api.config import CALENDAR_DB, SEED_USER
from api.db import bump, connect as _connect, get_version
from api.models import EventIn, EventPatch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calendars (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    owner  TEXT,
    name   TEXT NOT NULL,
    color  TEXT NOT NULL DEFAULT '#8b93a1',
    shared INTEGER NOT NULL DEFAULT 0,
    -- Who else it is shared with: {"<user>": "see"|"edit"|"manage"}.
    people TEXT NOT NULL DEFAULT '{}'
);
-- Guards _ensure_default_calendar's check-then-insert against a race (two
-- concurrent requests both seeing "no calendar yet" and both inserting one —
-- e.g. React StrictMode firing the same effect twice in quick succession).
-- SQLite treats NULLs as distinct for uniqueness, so this doesn't protect
-- the single shared-calendar row; init_db's own check is enough there since
-- it only ever runs once at process startup, not per-request.
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendars_owner_name ON calendars(owner, name);
CREATE TABLE IF NOT EXISTS calendar_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner          TEXT NOT NULL,
    calendar_id    INTEGER NOT NULL REFERENCES calendars(id),
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    start_date     TEXT NOT NULL,
    end_date       TEXT NOT NULL,
    all_day        INTEGER NOT NULL DEFAULT 1,
    start_time     TEXT,
    end_time       TEXT,
    recur_freq     TEXT,
    recur_interval INTEGER NOT NULL DEFAULT 1,
    recur_until    TEXT,
    recur_exceptions TEXT NOT NULL DEFAULT '[]',
    -- alarm: whether this event should alert at all. alarm_ack's shape
    -- depends on recurrence (see _validate_alarm_ack): "" (not acknowledged);
    -- else "true" for a plain event, or the date (YYYY-MM-DD) of the last
    -- occurrence acknowledged for a recurring one -- the frontend compares
    -- that against the series' latest visible occurrence to decide whether
    -- the alarm is still due.
    -- alarm_snooze_* is the temporary version of the same idea: while
    -- alarm_snooze_until (epoch milliseconds) is still in the future *and*
    -- alarm_snooze_occurrence still matches the occurrence currently due,
    -- the alarm stays hidden without being permanently acknowledged. Storing
    -- which occurrence it belongs to (not just a bare timestamp) is what
    -- makes a newer occurrence of a recurring series immediately override a
    -- snooze meant for an older one, instead of inheriting it.
    alarm          INTEGER NOT NULL DEFAULT 0,
    alarm_ack      TEXT,
    alarm_snooze_occurrence TEXT,
    alarm_snooze_until      INTEGER,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_span ON calendar_events(start_date, end_date);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_CALENDAR_NAME = "Default"
# What someone a calendar is shared with may do, least to most; the owner
# is above them all.
_RANK = {"see": 1, "edit": 2, "manage": 3, "owner": 4}
# Rotated through by id so a user's calendars aren't all the same colour by
# default; still freely changeable afterwards via update_calendar.
_DEFAULT_PALETTE = ["#4c9be8", "#e5484d", "#46a758", "#e93d82", "#f2c14e"]
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_RECUR_FREQS = {"daily", "weekly", "monthly", "yearly"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_VERSION_KEY = "calendar_version"


class CalendarError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@contextmanager
def connect():
    with _connect(CALENDAR_DB) as conn:
        yield conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database already existed in the wild —
    CREATE TABLE IF NOT EXISTS in _SCHEMA only covers a brand-new DB."""
    cal_cols = {r["name"] for r in conn.execute("PRAGMA table_info(calendars)")}
    if "shared" not in cal_cols:
        conn.execute("ALTER TABLE calendars ADD COLUMN shared INTEGER NOT NULL DEFAULT 0")
        # Pre-migration, "shared" was implicit: the one calendar with no
        # owner. Carry that forward as an explicitly-shared row instead of
        # silently hiding it from everyone.
        conn.execute("UPDATE calendars SET shared = 1 WHERE owner IS NULL")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(calendar_events)")}
    if "alarm" not in cols:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN alarm INTEGER NOT NULL DEFAULT 0")
    if "alarm_ack" not in cols:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN alarm_ack TEXT")
    if "alarm_snooze_occurrence" not in cols:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN alarm_snooze_occurrence TEXT")
    if "alarm_snooze_until" not in cols:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN alarm_snooze_until INTEGER")
    if "people" not in cal_cols:
        # Sharing became per person. What was shared was shared with
        # everyone, events editable by all: every user gets "edit" on it.
        # The one calendar from before calendars had owners gets one — the
        # seed user — since only an owner can now manage a calendar.
        from api.auth import USERS
        conn.execute("ALTER TABLE calendars ADD COLUMN people TEXT NOT NULL DEFAULT '{}'")
        conn.execute("UPDATE calendars SET owner = ? WHERE owner IS NULL", (SEED_USER,))
        for r in conn.execute("SELECT id, owner FROM calendars WHERE shared = 1").fetchall():
            people = {u: "edit" for u in USERS if u != r["owner"]}
            conn.execute("UPDATE calendars SET people = ? WHERE id = ?", (json.dumps(people), r["id"]))


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, 0)", (_VERSION_KEY,))


def version(conn: sqlite3.Connection) -> int:
    return get_version(conn, _VERSION_KEY)


def _next_palette_color(conn: sqlite3.Connection) -> str:
    n = conn.execute("SELECT COUNT(*) FROM calendars WHERE owner IS NOT NULL").fetchone()[0]
    return _DEFAULT_PALETTE[n % len(_DEFAULT_PALETTE)]


def _ensure_default_calendar(conn: sqlite3.Connection, user: str) -> None:
    # INSERT OR IGNORE (not a check-then-insert) so two concurrent callers —
    # e.g. React StrictMode firing the same effect twice — can't both see
    # "no calendar yet" and both insert one; the unique index makes the
    # second attempt a no-op instead of a duplicate row.
    conn.execute(
        "INSERT OR IGNORE INTO calendars(owner, name, color) VALUES(?, ?, ?)",
        (user, DEFAULT_CALENDAR_NAME, _next_palette_color(conn)),
    )


def _people(row: sqlite3.Row) -> dict[str, str]:
    try:
        p = json.loads(row["people"] or "{}")
        return p if isinstance(p, dict) else {}
    except ValueError:
        return {}


def _level(row: sqlite3.Row, user: str) -> str | None:
    """What `user` may do with this calendar: "owner", one of the people
    levels, or None — not shared with them, so not there for them."""
    if row["owner"] == user:
        return "owner"
    return _people(row).get(user)


def _allows(level: str | None, need: str) -> bool:
    return _RANK.get(level or "", 0) >= _RANK[need]


def _calendar_levels(conn: sqlite3.Connection, user: str) -> dict[int, str]:
    """Every calendar this user can see, with what they may do there."""
    out = {}
    for r in conn.execute("SELECT id, owner, people FROM calendars").fetchall():
        level = _level(r, user)
        if level:
            out[r["id"]] = level
    return out


def list_calendars(conn: sqlite3.Connection, user: str) -> list[dict]:
    """The user's own calendars (oldest — i.e. their Default — first) followed
    by the ones shared with them. `mine`: they may rename, recolour and share
    it (its owner, or "manage"); `level`: what they may do there; `people`
    shown to whoever may change it."""
    _ensure_default_calendar(conn, user)
    rows = conn.execute("SELECT * FROM calendars ORDER BY (owner IS NOT ?), id", (user,)).fetchall()
    out = []
    for r in rows:
        level = _level(r, user)
        if not level:
            continue
        people = _people(r)
        cal = {
            "id": r["id"], "name": r["name"], "color": r["color"],
            "shared": bool(people),
            "mine": _allows(level, "manage"),
            "owner": r["owner"],
            "level": level,
        }
        if _allows(level, "manage"):
            cal["people"] = people
        out.append(cal)
    return out


def _validate_color(color: str) -> None:
    if not _COLOR_RE.match(color):
        raise CalendarError("color must be a hex code like #4c9be8")


def create_calendar(
    conn: sqlite3.Connection, user: str, name: str, color: str | None = None, shared: bool = False,
) -> list[dict]:
    name = name.strip()
    if not name:
        raise CalendarError("calendar name is required")
    if color is not None:
        _validate_color(color)
    else:
        color = _next_palette_color(conn)
    try:
        people = _everyone(user) if shared else {}
        conn.execute(
            "INSERT INTO calendars(owner, name, color, shared, people) VALUES(?, ?, ?, ?, ?)",
            (user, name, color, int(bool(people)), json.dumps(people)),
        )
    except sqlite3.IntegrityError:
        raise CalendarError(f"you already have a calendar named {name!r}")
    return list_calendars(conn, user)


def _everyone(owner: str) -> dict[str, str]:
    """Shared with every user, events editable by all — what `shared: true`
    meant before sharing was per person, still what the clients' share
    toggle asks for."""
    from api.auth import USERS
    return {u: "edit" for u in USERS if u != owner}


def _get_calendar(conn: sqlite3.Connection, user: str, calendar_id: int, need: str) -> sqlite3.Row:
    """The calendar, if `user` may do `need` there ("see", "edit", "manage",
    "owner"). One not shared with them is not found, as if it did not exist."""
    row = conn.execute("SELECT * FROM calendars WHERE id = ?", (calendar_id,)).fetchone()
    level = _level(row, user) if row is not None else None
    if not level:
        raise CalendarError("calendar not found", status_code=404)
    if not _allows(level, need):
        raise CalendarError("not permitted on this calendar", status_code=403)
    return row


def update_calendar(conn: sqlite3.Connection, user: str, calendar_id: int,
                     name: str | None, color: str | None, shared: bool | None = None) -> list[dict]:
    """Rename or recolour, for its owner and whoever may manage it. `shared`
    is the clients' simple toggle: true shares it with everyone (events
    editable by all), false makes it private again — set_sharing() says it
    person by person."""
    row = _get_calendar(conn, user, calendar_id, "manage")
    fields: dict[str, str | int] = {}
    if name is not None:
        name = name.strip()
        if not name:
            raise CalendarError("calendar name is required")
        fields["name"] = name
    if color is not None:
        _validate_color(color)
        fields["color"] = color
    if shared is not None:
        people = _everyone(row["owner"]) if shared else {}
        fields["people"] = json.dumps(people)
        fields["shared"] = int(bool(people))
    if fields:
        try:
            conn.execute(
                f"UPDATE calendars SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                (*fields.values(), calendar_id),
            )
        except sqlite3.IntegrityError:
            raise CalendarError(f"you already have a calendar named {name!r}")
        bump(conn, _VERSION_KEY)  # event listings embed calendar name/color
    return list_calendars(conn, user)


def set_sharing(conn: sqlite3.Connection, user: str, calendar_id: int, people: dict[str, str]) -> list[dict]:
    """Who else sees the calendar and what they may do: {"<user>": "see" |
    "edit" | "manage"}; {} is private. For its owner and whoever may manage
    it; the owner is always the owner and is not one of the people."""
    from api.auth import USERS
    row = _get_calendar(conn, user, calendar_id, "manage")
    clean = {}
    for name, level in (people or {}).items():
        if name not in USERS:
            raise CalendarError(f"no user called {name!r}")
        if level not in ("see", "edit", "manage"):
            raise CalendarError("a person's access is see, edit or manage")
        if name != row["owner"]:
            clean[name] = level
    conn.execute("UPDATE calendars SET people = ?, shared = ? WHERE id = ?",
                 (json.dumps(clean), int(bool(clean)), calendar_id))
    bump(conn, _VERSION_KEY)
    return list_calendars(conn, user)


def sharing_users() -> list[str]:
    """Who a calendar can be shared with: everyone who can open the Calendar."""
    from api.auth import USERS, visible_panels
    return sorted(u for u in USERS if (visible_panels(u) is None or "calendar" in visible_panels(u)))


def delete_calendar(conn: sqlite3.Connection, user: str, calendar_id: int) -> list[dict]:
    """Cascades: every event filed under this calendar is deleted with it.
    Only its owner may."""
    _get_calendar(conn, user, calendar_id, "owner")
    conn.execute("DELETE FROM calendar_events WHERE calendar_id = ?", (calendar_id,))
    conn.execute("DELETE FROM calendars WHERE id = ?", (calendar_id,))
    bump(conn, _VERSION_KEY)
    return list_calendars(conn, user)


def _check_calendar_access(conn: sqlite3.Connection, user: str, calendar_id: int) -> None:
    """Filing an event into a calendar: its owner, or someone who may edit."""
    _get_calendar(conn, user, calendar_id, "edit")


def _row_to_event(row: sqlite3.Row, user: str, start_date: str | None = None,
                   end_date: str | None = None, level: str | None = None) -> dict:
    """`start_date`/`end_date` override the stored ones for one computed
    occurrence of a recurring event; omitted for a plain, non-recurring one."""
    return {
        "id": row["id"],
        "owner": row["owner"],
        "mine": row["owner"] == user,
        "calendar_id": row["calendar_id"],
        "calendar_name": row["calendar_name"],
        "calendar_color": row["calendar_color"],
        # "May change this event": the clients offer editing when this or
        # `mine` is true. Named for what it used to mean — a shared
        # calendar's events were everyone's.
        "calendar_shared": _allows(level, "edit"),
        "editable": _allows(level, "edit"),
        "calendar_level": level,
        "title": row["title"],
        "description": row["description"],
        "start_date": start_date or row["start_date"],
        "end_date": end_date or row["end_date"],
        "all_day": bool(row["all_day"]),
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "recur_freq": row["recur_freq"],
        "recur_interval": row["recur_interval"],
        "recur_until": row["recur_until"],
        "recurring": row["recur_freq"] is not None,
        "alarm": bool(row["alarm"]),
        "alarm_ack": row["alarm_ack"],
        "alarm_snooze_occurrence": row["alarm_snooze_occurrence"],
        "alarm_snooze_until": row["alarm_snooze_until"],
    }


def _next_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01"


def _month_bounds(month: str) -> tuple[date, date]:
    y, m = (int(x) for x in month.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    next_month_first = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    last_day_of_month = (next_month_first - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day_of_month))


def _occurrence_starts(start: date, freq: str, interval: int, until: date | None,
                        range_start: date, range_end_excl: date) -> list[date]:
    """Every occurrence start-date of one recurring series that falls in
    [range_start, range_end_excl) — computed directly rather than walked one
    step at a time, so a daily series anchored years ago is just as cheap to
    query as one that started last week."""
    out: list[date] = []
    if freq in ("daily", "weekly"):
        step_days = interval if freq == "daily" else interval * 7
        first_k = max(0, -((range_start - start).days // -step_days))  # ceil division
        d = start + timedelta(days=first_k * step_days)
        while d < range_end_excl:
            if d >= start and (until is None or d <= until):
                out.append(d)
            d += timedelta(days=step_days)
    elif freq in ("monthly", "yearly"):
        step_months = interval if freq == "monthly" else interval * 12
        months_between = (range_start.year - start.year) * 12 + (range_start.month - start.month)
        # A handful of candidates around the estimate covers any rounding
        # from day-of-month clamping (e.g. day 31 landing earlier some months).
        k0 = max(0, months_between // step_months - 1)
        for k in range(k0, k0 + 4):
            d = _add_months(start, k * step_months)
            if d >= range_end_excl:
                break
            if range_start <= d < range_end_excl and d >= start and (until is None or d <= until):
                out.append(d)
    return out


def list_month(conn: sqlite3.Connection, user: str, month: str) -> dict:
    """Every event whose span overlaps the month — including one that started
    earlier and/or ends later — plus every occurrence of a recurring event
    that falls in the month, computed fresh on each call."""
    range_start, range_end = _month_bounds(month)
    levels = _calendar_levels(conn, user)
    rows = conn.execute(
        "SELECT e.*, c.name AS calendar_name, c.color AS calendar_color "
        "FROM calendar_events e JOIN calendars c ON e.calendar_id = c.id "
        f"WHERE c.id IN ({','.join('?' * len(levels))}) "
        "AND (e.recur_freq IS NOT NULL OR (e.end_date >= ? AND e.start_date < ?))",
        (*levels, range_start.isoformat(), range_end.isoformat()),
    ).fetchall() if levels else []

    events = []
    for row in rows:
        if row["recur_freq"] is None:
            events.append(_row_to_event(row, user, level=levels[row["calendar_id"]]))
            continue
        start = date.fromisoformat(row["start_date"])
        duration = date.fromisoformat(row["end_date"]) - start
        until = date.fromisoformat(row["recur_until"]) if row["recur_until"] else None
        exceptions = set(json.loads(row["recur_exceptions"] or "[]"))
        for occ_start in _occurrence_starts(
            start, row["recur_freq"], row["recur_interval"], until, range_start, range_end,
        ):
            if occ_start.isoformat() in exceptions:
                continue
            events.append(_row_to_event(row, user, occ_start.isoformat(), (occ_start + duration).isoformat(),
                                        level=levels[row["calendar_id"]]))

    events.sort(key=lambda e: (e["start_date"], not e["all_day"], e["start_time"] or ""))
    return {
        "month": month,
        "events": events,
        "calendar_version": version(conn),
    }


def _validate_span(start_date: str, end_date: str, all_day: bool,
                    start_time: str | None, end_time: str | None) -> None:
    if end_date < start_date:
        raise CalendarError("end date must not be before start date")
    if not all_day:
        if not start_time or not end_time:
            raise CalendarError("start_time and end_time are required unless all_day")
        if end_date == start_date and end_time <= start_time:
            raise CalendarError("end time must be after start time")


def _validate_recurrence(freq: str | None, interval: int, until: str | None, start_date: str) -> None:
    if freq is None:
        return
    if freq not in _RECUR_FREQS:
        raise CalendarError(f"invalid recur_freq {freq!r}")
    if interval < 1:
        raise CalendarError("recur_interval must be at least 1")
    if until and until < start_date:
        raise CalendarError("recur_until must not be before start date")


def _validate_alarm_ack(alarm_ack: str | None, recur_freq: str | None) -> None:
    """alarm_ack's required shape depends on whether the event recurs: ""
    (not acknowledged) is always fine; otherwise a recurring event needs a
    YYYY-MM-DD date (the last occurrence acknowledged) and a plain one needs
    the literal string "true"."""
    if not alarm_ack:
        return
    if recur_freq is not None:
        if not _ISO_DATE_RE.match(alarm_ack):
            raise CalendarError('alarm_ack must be "" or a YYYY-MM-DD date for a recurring event')
    elif alarm_ack != "true":
        raise CalendarError('alarm_ack must be "" or "true" for a non-recurring event')


def _validate_snooze(occurrence: str | None, until: int | None) -> None:
    """Both fields travel together -- a snooze without knowing which
    occurrence it's for is meaningless, and a bare occurrence with no
    timestamp doesn't suppress anything."""
    if occurrence is None and until is None:
        return
    if occurrence is None or until is None:
        raise CalendarError(
            "alarm_snooze_occurrence and alarm_snooze_until must be set or cleared together"
        )
    if not _ISO_DATE_RE.match(occurrence):
        raise CalendarError("alarm_snooze_occurrence must be a YYYY-MM-DD date")
    if not isinstance(until, int) or isinstance(until, bool) or until <= 0:
        raise CalendarError("alarm_snooze_until must be a positive integer (epoch milliseconds)")


def _validate_new_event(conn: sqlite3.Connection, user: str, body: EventIn) -> None:
    _check_calendar_access(conn, user, body.calendar_id)
    _validate_span(body.start_date, body.end_date, body.all_day, body.start_time, body.end_time)
    _validate_recurrence(body.recur_freq, body.recur_interval, body.recur_until, body.start_date)
    _validate_alarm_ack(body.alarm_ack, body.recur_freq)


def _insert_event(conn: sqlite3.Connection, user: str, body: EventIn) -> int:
    cur = conn.execute(
        "INSERT INTO calendar_events(owner, calendar_id, title, description, start_date, end_date, "
        "all_day, start_time, end_time, recur_freq, recur_interval, recur_until, alarm, alarm_ack, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user, body.calendar_id, body.title, body.description, body.start_date, body.end_date,
            int(body.all_day), None if body.all_day else body.start_time,
            None if body.all_day else body.end_time,
            body.recur_freq, body.recur_interval, body.recur_until,
            int(body.alarm), body.alarm_ack,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return cur.lastrowid


def create_event(conn: sqlite3.Connection, user: str, body: EventIn) -> dict:
    _validate_new_event(conn, user, body)
    _insert_event(conn, user, body)
    bump(conn, _VERSION_KEY)
    return list_month(conn, user, body.start_date[:7])


def create_events_bulk(conn: sqlite3.Connection, user: str, bodies: list[EventIn]) -> list[dict]:
    """Insert every event in `bodies` together. Every entry is validated
    first and only then inserted -- one bad entry anywhere in the list fails
    (and, since the caller's `connect()` rolls back on any exception) leaves
    the whole batch uninserted, rather than importing part of it."""
    if not bodies:
        return []
    for body in bodies:
        _validate_new_event(conn, user, body)
    ids = [_insert_event(conn, user, body) for body in bodies]
    bump(conn, _VERSION_KEY)
    rows = conn.execute(
        "SELECT e.*, c.name AS calendar_name, c.color AS calendar_color FROM calendar_events e "
        f"JOIN calendars c ON c.id = e.calendar_id WHERE e.id IN ({','.join('?' * len(ids))})",
        ids,
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    levels = _calendar_levels(conn, user)
    return [_row_to_event(by_id[i], user, level=levels.get(by_id[i]["calendar_id"])) for i in ids]


def _get_editable(conn: sqlite3.Connection, user: str, event_id: int, need: str = "edit") -> sqlite3.Row:
    """An event, if its calendar lets `user` do `need` ("edit" to change or
    delete it; "see" is enough for its alarm). An event on a calendar not
    shared with them is not found."""
    row = conn.execute(
        "SELECT e.*, c.owner AS calendar_owner, c.people AS people FROM calendar_events e "
        "JOIN calendars c ON c.id = e.calendar_id WHERE e.id = ?",
        (event_id,),
    ).fetchone()
    level = None
    if row is not None:
        level = "owner" if row["calendar_owner"] == user else _people(row).get(user)
    if not level:
        raise CalendarError("event not found", status_code=404)
    if not _allows(level, need):
        raise CalendarError("this calendar is shared with you to look at, not to change", status_code=403)
    return row


# Changing only these is acknowledging or snoozing an alarm — allowed to
# anyone who sees the event.
_ALARM_FIELDS = {"alarm_ack", "alarm_snooze_occurrence", "alarm_snooze_until"}


def update_event(conn: sqlite3.Connection, user: str, event_id: int, body: EventPatch) -> dict:
    fields = body.model_dump(exclude_unset=True)
    row = _get_editable(conn, user, event_id, "see" if fields and set(fields) <= _ALARM_FIELDS else "edit")

    if "calendar_id" in fields:
        _check_calendar_access(conn, user, fields["calendar_id"])

    start_date = fields.get("start_date", row["start_date"])
    end_date = fields.get("end_date", row["end_date"])
    all_day = fields.get("all_day", bool(row["all_day"]))
    start_time = fields.get("start_time", row["start_time"])
    end_time = fields.get("end_time", row["end_time"])
    if all_day:
        start_time = end_time = None
    _validate_span(start_date, end_date, all_day, start_time, end_time)

    # A moved event invalidates whatever ack/snooze applied to it at its old
    # time -- e.g. rescheduling a 9am meeting to 2pm shouldn't inherit the
    # fact that 9am's alarm was already dismissed, and a snooze keyed to the
    # old start_date would otherwise keep suppressing the alarm at the new
    # time whenever only start_time changed (start_date staying the same
    # would still match the stored snooze occurrence). An explicit alarm_ack/
    # snooze value in the same request still wins over this default.
    moved = (
        start_date != row["start_date"]
        or start_time != row["start_time"]
        or int(all_day) != row["all_day"]
    )
    if moved:
        fields.setdefault("alarm_ack", "")
        fields.setdefault("alarm_snooze_occurrence", None)
        fields.setdefault("alarm_snooze_until", None)

    recur_freq = fields.get("recur_freq", row["recur_freq"])
    recur_interval = fields.get("recur_interval", row["recur_interval"])
    recur_until = fields.get("recur_until", row["recur_until"])
    _validate_recurrence(recur_freq, recur_interval, recur_until, start_date)
    alarm_ack = fields.get("alarm_ack", row["alarm_ack"])
    _validate_alarm_ack(alarm_ack, recur_freq)
    snooze_occurrence = fields.get("alarm_snooze_occurrence", row["alarm_snooze_occurrence"])
    snooze_until = fields.get("alarm_snooze_until", row["alarm_snooze_until"])
    _validate_snooze(snooze_occurrence, snooze_until)

    fields["start_date"] = start_date
    fields["end_date"] = end_date
    fields["start_time"] = start_time
    fields["end_time"] = end_time
    fields["all_day"] = int(all_day)
    fields["recur_freq"] = recur_freq
    fields["recur_interval"] = recur_interval
    fields["recur_until"] = recur_until

    conn.execute(
        f"UPDATE calendar_events SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
        (*fields.values(), event_id),
    )
    bump(conn, _VERSION_KEY)
    return list_month(conn, user, start_date[:7])


def delete_event(conn: sqlite3.Connection, user: str, event_id: int, occurrence: str | None = None) -> dict:
    """`occurrence` ("delete this event", only meaningful for a recurring
    series) adds that one date to recur_exceptions instead of removing the
    row, so the rest of the series is untouched. Without it — or when the
    event isn't recurring, where there's only ever one occurrence anyway —
    the whole row is removed ("delete series")."""
    row = _get_editable(conn, user, event_id)
    month = (occurrence or row["start_date"])[:7]
    if occurrence and row["recur_freq"] is not None:
        exceptions = set(json.loads(row["recur_exceptions"] or "[]"))
        exceptions.add(occurrence)
        conn.execute(
            "UPDATE calendar_events SET recur_exceptions = ? WHERE id = ?",
            (json.dumps(sorted(exceptions)), event_id),
        )
    else:
        conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
    bump(conn, _VERSION_KEY)
    return list_month(conn, user, month)


def delete_events_from(
    conn: sqlite3.Connection, user: str, from_date: str, calendar_id: int | None = None,
) -> int:
    """Deletes every event whose own start_date is on or after `from_date`
    (inclusive), among calendars this user may edit (their own, or one shared with
    them to edit -- same access rule as _get_editable). `calendar_id`, when
    given, narrows this to just that one calendar (still access-checked --
    404/403 the same way filing an event into it would); omitted, every
    editable calendar is in scope, as before this parameter existed. For a
    recurring series this looks at the row's own anchor start_date, not its
    individual occurrences -- a weekly series that started before `from_date`
    is left alone even though some of its future occurrences fall after it,
    since deleting "some occurrences" isn't a thing the schema represents
    (there's one row per series, not per occurrence). Returns the number of
    rows deleted."""
    if calendar_id is not None:
        _check_calendar_access(conn, user, calendar_id)
    editable = [cid for cid, level in _calendar_levels(conn, user).items() if _allows(level, "edit")]
    if not editable:
        return 0
    query = (
        "SELECT e.id FROM calendar_events e "
        f"WHERE e.start_date >= ? AND e.calendar_id IN ({','.join('?' * len(editable))})"
    )
    params: list = [from_date, *editable]
    if calendar_id is not None:
        query += " AND e.calendar_id = ?"
        params.append(calendar_id)
    rows = conn.execute(query, params).fetchall()
    ids = [r["id"] for r in rows]
    if ids:
        conn.execute(f"DELETE FROM calendar_events WHERE id IN ({','.join('?' * len(ids))})", ids)
        bump(conn, _VERSION_KEY)
    return len(ids)
