"""Diary CRUD on top of the SQLite store. Every row is scoped to a `user` and
every query filters on it. Every mutating helper bumps the user's
`"<user>:diary_version"` counter and returns fresh state so the change request's
reply already carries what the UI should render."""
import calendar
import datetime as _dt
import json
import re
import sqlite3
from typing import Any

from api.db import bump, diary_version_key, get_version
from api.models import BulkRow, ColumnIn, ColumnPatch

_TYPES = {"number", "text", "bool", "enum"}


def _clean_options(raw) -> list[str]:
    return [str(o).strip() for o in (raw or []) if str(o).strip()]


def current_month() -> str:
    t = _dt.date.today()
    return f"{t.year:04d}-{t.month:02d}"


def _bump(conn: sqlite3.Connection, user: str) -> None:
    bump(conn, diary_version_key(user))


# ── columns ────────────────────────────────────────────────────────────────
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "col"


def _unique_key(conn: sqlite3.Connection, user: str, name: str) -> str:
    taken = {r["key"] for r in conn.execute(
        "SELECT key FROM diary_columns WHERE username = ?", (user,))}
    base = _slug(name)
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    return key


def column_exists(conn: sqlite3.Connection, user: str, key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM diary_columns WHERE username = ? AND key = ?", (user, key)
    ).fetchone() is not None


def _row_to_column(r: sqlite3.Row) -> dict:
    d = {k: r[k] for k in r.keys()}
    d.pop("username", None)
    try:
        d["options"] = json.loads(d.get("options") or "[]")
    except (TypeError, ValueError):
        d["options"] = []
    return d


def list_columns(conn: sqlite3.Connection, user: str) -> list[dict]:
    rows = conn.execute(
        "SELECT key,name,description,unit,type,position,options FROM diary_columns "
        "WHERE username = ? ORDER BY position, key",
        (user,),
    ).fetchall()
    return [_row_to_column(r) for r in rows]


def create_column(conn: sqlite3.Connection, user: str, data: ColumnIn, month: str) -> dict:
    key = _unique_key(conn, user, data.name)
    pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM diary_columns WHERE username = ?",
        (user,),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO diary_columns(username,key,name,description,unit,type,position,options) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (user, key, data.name.strip(), data.description.strip(), data.unit.strip(),
         data.type, pos, json.dumps(_clean_options(data.options))),
    )
    _remember_unit(conn, user, data.unit)
    _bump(conn, user)
    return get_month(conn, user, month)


def patch_column(conn: sqlite3.Connection, user: str, key: str, patch: ColumnPatch, month: str) -> dict:
    fields = patch.model_dump(exclude_none=True)
    if "type" in fields and fields["type"] not in _TYPES:
        fields.pop("type")
    for col in ("name", "description", "unit"):
        if col in fields:
            fields[col] = str(fields[col]).strip()
    if "options" in fields:
        fields["options"] = json.dumps(_clean_options(fields["options"]))
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE diary_columns SET {sets} WHERE username = ? AND key = ?",
                     (*fields.values(), user, key))
        if "unit" in fields:
            _remember_unit(conn, user, fields["unit"])
    _bump(conn, user)
    return get_month(conn, user, month)


def delete_column(conn: sqlite3.Connection, user: str, key: str, month: str) -> dict:
    conn.execute("DELETE FROM diary_entries WHERE username = ? AND key = ?", (user, key))
    conn.execute("DELETE FROM diary_columns WHERE username = ? AND key = ?", (user, key))
    _bump(conn, user)
    return get_month(conn, user, month)


def reorder_columns(conn: sqlite3.Connection, user: str, keys: list[str], month: str) -> dict:
    """Assign positions 0..n-1 from the given key order. Unknown keys are
    ignored; columns missing from `keys` keep their old position value and so
    sort after the reordered ones."""
    for i, key in enumerate(keys):
        conn.execute(
            "UPDATE diary_columns SET position = ? WHERE username = ? AND key = ?",
            (i, user, key),
        )
    _bump(conn, user)
    return get_month(conn, user, month)


# ── units ──────────────────────────────────────────────────────────────────
def list_units(conn: sqlite3.Connection, user: str) -> list[str]:
    return [r["unit"] for r in conn.execute(
        "SELECT unit FROM diary_units WHERE username = ? ORDER BY position, unit", (user,)
    )]


def _remember_unit(conn: sqlite3.Connection, user: str, unit: str) -> None:
    unit = (unit or "").strip()
    if not unit:
        return
    pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM diary_units WHERE username = ?",
        (user,),
    ).fetchone()[0]
    conn.execute("INSERT OR IGNORE INTO diary_units(username,unit,position) VALUES(?,?,?)",
                 (user, unit, pos))


def add_unit(conn: sqlite3.Connection, user: str, unit: str, month: str) -> dict:
    _remember_unit(conn, user, unit)
    _bump(conn, user)
    return get_month(conn, user, month)


def remove_unit(conn: sqlite3.Connection, user: str, unit: str, month: str) -> dict:
    """Drop a unit from the pick-list. Columns already using it keep their label
    (unit is stored on the column row, not a foreign key)."""
    conn.execute("DELETE FROM diary_units WHERE username = ? AND unit = ?", (user, unit))
    _bump(conn, user)
    return get_month(conn, user, month)


# ── entries ────────────────────────────────────────────────────────────────
def _cast(value: str | None, ctype: str) -> Any:
    if value is None or value == "":
        return None
    if ctype == "number":
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except ValueError:
            return None
    if ctype == "bool":
        return str(value).strip().lower() in {"true", "1", "yes", "y"}
    return value


def _serialize(value: Any, ctype: str) -> str | None:
    if ctype == "bool":
        truthy = value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}
        return "true" if truthy else None
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def get_month(conn: sqlite3.Connection, user: str, month: str) -> dict:
    """month = 'YYYY-MM'. Returns one row per calendar day, always."""
    y, m = (int(x) for x in month.split("-"))
    ndays = calendar.monthrange(y, m)[1]
    cols = list_columns(conn, user)
    ctype = {c["key"]: c["type"] for c in cols}

    rows = {f"{y:04d}-{m:02d}-{d:02d}": {} for d in range(1, ndays + 1)}
    for r in conn.execute(
        "SELECT date,key,value FROM diary_entries WHERE username = ? AND date LIKE ?",
        (user, f"{y:04d}-{m:02d}-%"),
    ):
        if r["date"] in rows and r["key"] in ctype:
            rows[r["date"]][r["key"]] = _cast(r["value"], ctype[r["key"]])

    return {
        "month": month,
        "columns": cols,
        "units": list_units(conn, user),
        "rows": [{"date": d, "values": rows[d]} for d in sorted(rows)],
        "version": get_version(conn, diary_version_key(user)),
    }


def _write_day(conn: sqlite3.Connection, user: str, ctype: dict[str, str], d: str,
               values: dict[str, Any]) -> None:
    for k, v in values.items():
        if k not in ctype:
            continue
        s = _serialize(v, ctype[k])
        if s is None:
            conn.execute("DELETE FROM diary_entries WHERE username=? AND date=? AND key=?",
                         (user, d, k))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO diary_entries(username,date,key,value) VALUES(?,?,?,?)",
                (user, d, k, s),
            )


def put_day(conn: sqlite3.Connection, user: str, d: str, values: dict[str, Any]) -> dict:
    ctype = {c["key"]: c["type"] for c in list_columns(conn, user)}
    _write_day(conn, user, ctype, d, values)
    _bump(conn, user)
    return get_month(conn, user, d[:7])


def put_bulk(conn: sqlite3.Connection, user: str, rows: list[BulkRow]) -> dict:
    ctype = {c["key"]: c["type"] for c in list_columns(conn, user)}
    for row in rows:
        _write_day(conn, user, ctype, row.date, row.values)
    _bump(conn, user)
    month = rows[0].date[:7] if rows else None
    return (get_month(conn, user, month) if month
            else {"version": get_version(conn, diary_version_key(user))})
