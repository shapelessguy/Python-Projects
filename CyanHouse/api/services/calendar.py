"""Calendar service storage — a self-contained module (own SQLite file, own
version counter), mirroring food.py's template. No external account: every
event lives only in this DB.

Two kinds of event, told apart by the `shared` flag:
  - personal (shared=0): visible only to its owner.
  - shared   (shared=1): visible to every CyanHouse user.

Either way, only the creator can edit or delete their own event — a shared
event is visible to everyone but not up for grabs by everyone, which avoids
one user's edit silently overwriting another's.

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
Consequently editing or deleting acts on the whole series, not a single
occurrence — there's no per-occurrence exception support (a "skip just this
one" or "change just this one") in this version.

A single global `calendar_version` counter covers both kinds (like
weather_version) rather than a per-user one: a shared event changing is
relevant to everyone anyway, and the extra precision of scoping personal-only
changes to just their owner isn't worth the complexity here."""
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from api.config import CALENDAR_DB
from api.db import bump, connect as _connect, get_version
from api.models import EventIn, EventPatch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner          TEXT NOT NULL,
    shared         INTEGER NOT NULL DEFAULT 0,
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
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_span ON calendar_events(start_date, end_date);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""

_RECUR_FREQS = {"daily", "weekly", "monthly", "yearly"}

_VERSION_KEY = "calendar_version"


class CalendarError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@contextmanager
def connect():
    with _connect(CALENDAR_DB) as conn:
        yield conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, 0)", (_VERSION_KEY,))


def version(conn: sqlite3.Connection) -> int:
    return get_version(conn, _VERSION_KEY)


def _row_to_event(row: sqlite3.Row, user: str, start_date: str | None = None,
                   end_date: str | None = None) -> dict:
    """`start_date`/`end_date` override the stored ones for one computed
    occurrence of a recurring event; omitted for a plain, non-recurring one."""
    return {
        "id": row["id"],
        "owner": row["owner"],
        "mine": row["owner"] == user,
        "shared": bool(row["shared"]),
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
    rows = conn.execute(
        "SELECT * FROM calendar_events WHERE (shared = 1 OR owner = ?) "
        "AND (recur_freq IS NOT NULL OR (end_date >= ? AND start_date < ?))",
        (user, range_start.isoformat(), range_end.isoformat()),
    ).fetchall()

    events = []
    for row in rows:
        if row["recur_freq"] is None:
            events.append(_row_to_event(row, user))
            continue
        start = date.fromisoformat(row["start_date"])
        duration = date.fromisoformat(row["end_date"]) - start
        until = date.fromisoformat(row["recur_until"]) if row["recur_until"] else None
        for occ_start in _occurrence_starts(
            start, row["recur_freq"], row["recur_interval"], until, range_start, range_end,
        ):
            events.append(_row_to_event(row, user, occ_start.isoformat(), (occ_start + duration).isoformat()))

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


def create_event(conn: sqlite3.Connection, user: str, body: EventIn) -> dict:
    _validate_span(body.start_date, body.end_date, body.all_day, body.start_time, body.end_time)
    _validate_recurrence(body.recur_freq, body.recur_interval, body.recur_until, body.start_date)
    conn.execute(
        "INSERT INTO calendar_events(owner, shared, title, description, start_date, end_date, "
        "all_day, start_time, end_time, recur_freq, recur_interval, recur_until, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user, int(body.shared), body.title, body.description, body.start_date, body.end_date,
            int(body.all_day), None if body.all_day else body.start_time,
            None if body.all_day else body.end_time,
            body.recur_freq, body.recur_interval, body.recur_until,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    bump(conn, _VERSION_KEY)
    return list_month(conn, user, body.start_date[:7])


def _get_owned(conn: sqlite3.Connection, user: str, event_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise CalendarError("event not found", status_code=404)
    if row["owner"] != user:
        raise CalendarError("only the creator can change this event", status_code=403)
    return row


def update_event(conn: sqlite3.Connection, user: str, event_id: int, body: EventPatch) -> dict:
    row = _get_owned(conn, user, event_id)
    fields = body.model_dump(exclude_unset=True)

    start_date = fields.get("start_date", row["start_date"])
    end_date = fields.get("end_date", row["end_date"])
    all_day = fields.get("all_day", bool(row["all_day"]))
    start_time = fields.get("start_time", row["start_time"])
    end_time = fields.get("end_time", row["end_time"])
    if all_day:
        start_time = end_time = None
    _validate_span(start_date, end_date, all_day, start_time, end_time)

    recur_freq = fields.get("recur_freq", row["recur_freq"])
    recur_interval = fields.get("recur_interval", row["recur_interval"])
    recur_until = fields.get("recur_until", row["recur_until"])
    _validate_recurrence(recur_freq, recur_interval, recur_until, start_date)

    fields["start_date"] = start_date
    fields["end_date"] = end_date
    fields["start_time"] = start_time
    fields["end_time"] = end_time
    fields["all_day"] = int(all_day)
    fields["recur_freq"] = recur_freq
    fields["recur_interval"] = recur_interval
    fields["recur_until"] = recur_until
    if "shared" in fields:
        fields["shared"] = int(fields["shared"])

    conn.execute(
        f"UPDATE calendar_events SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
        (*fields.values(), event_id),
    )
    bump(conn, _VERSION_KEY)
    return list_month(conn, user, start_date[:7])


def delete_event(conn: sqlite3.Connection, user: str, event_id: int) -> dict:
    row = _get_owned(conn, user, event_id)
    month = row["start_date"][:7]
    conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
    bump(conn, _VERSION_KEY)
    return list_month(conn, user, month)
