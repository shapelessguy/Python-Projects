import re

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import require_user
from api.db import connect
from api.models import BulkIn, ColumnIn, ColumnOrderIn, ColumnPatch, DayIn, UnitIn
from api.services import diary

router = APIRouter(prefix="/api/personal", tags=["personal"])

PANEL = "personal"  # gates the whole router behind permissions.visibility -- see api/auth.py

_MONTH_RE = r"^\d{4}-\d{2}$"
_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


def _month(month: str | None) -> str:
    """Every mutation reply is a full month snapshot; the client says which
    month it is looking at, else we use the current one."""
    if month and re.match(_MONTH_RE, month):
        return month
    return diary.current_month()


# ── columns ────────────────────────────────────────────────────────────────
@router.get("/columns")
def get_columns(user: str = Depends(require_user)):
    with connect() as conn:
        return diary.list_columns(conn, user)


@router.post("/columns")
def create_column(body: ColumnIn, month: str | None = Query(None),
                  user: str = Depends(require_user)):
    with connect() as conn:
        return diary.create_column(conn, user, body, _month(month))


@router.put("/columns/order")
def reorder_columns(body: ColumnOrderIn, month: str | None = Query(None),
                    user: str = Depends(require_user)):
    with connect() as conn:
        return diary.reorder_columns(conn, user, body.keys, _month(month))


@router.patch("/columns/{key}")
def patch_column(key: str, body: ColumnPatch, month: str | None = Query(None),
                 user: str = Depends(require_user)):
    with connect() as conn:
        if not diary.column_exists(conn, user, key):
            raise HTTPException(404, f"no column {key!r}")
        return diary.patch_column(conn, user, key, body, _month(month))


@router.delete("/columns/{key}")
def delete_column(key: str, month: str | None = Query(None),
                  user: str = Depends(require_user)):
    with connect() as conn:
        if not diary.column_exists(conn, user, key):
            raise HTTPException(404, f"no column {key!r}")
        return diary.delete_column(conn, user, key, _month(month))


# ── units ──────────────────────────────────────────────────────────────────
@router.get("/units")
def get_units(user: str = Depends(require_user)):
    with connect() as conn:
        return diary.list_units(conn, user)


@router.post("/units")
def add_unit(body: UnitIn, month: str | None = Query(None),
             user: str = Depends(require_user)):
    with connect() as conn:
        return diary.add_unit(conn, user, body.unit, _month(month))


@router.delete("/units")
def delete_unit(unit: str = Query(..., min_length=1), month: str | None = Query(None),
                user: str = Depends(require_user)):
    with connect() as conn:
        return diary.remove_unit(conn, user, unit, _month(month))


# ── entries ────────────────────────────────────────────────────────────────
@router.get("/entries")
def get_entries(month: str = Query(..., pattern=_MONTH_RE),
                user: str = Depends(require_user)):
    with connect() as conn:
        return diary.get_month(conn, user, month)


@router.put("/entries/{d}")
def put_day(d: str, body: DayIn, user: str = Depends(require_user)):
    if not re.match(_DATE_RE, d):
        raise HTTPException(422, "date must be YYYY-MM-DD")
    with connect() as conn:
        return diary.put_day(conn, user, d, body.values)


@router.patch("/entries")
def patch_entries(body: BulkIn, user: str = Depends(require_user)):
    with connect() as conn:
        return diary.put_bulk(conn, user, body.rows)
