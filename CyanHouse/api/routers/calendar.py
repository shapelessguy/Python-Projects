"""Calendar — personal + shared events, entirely local (no external account).
Personal events are visible only to their creator; shared events are visible
to every CyanHouse user. Self-contained module: own DB, own version counter —
see api/services/calendar.py and food.py's router for the template this
follows.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import require_user
from api.models import EventIn, EventPatch
from api.services import calendar

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

VERSION_NAMES = ["calendar"]

_MONTH_RE = r"^\d{4}-\d{2}$"


def init() -> None:
    calendar.init_db()


def versions(user: str | None) -> dict[str, int]:
    with calendar.connect() as conn:
        return {"calendar": calendar.version(conn)}


@router.get("/events")
def get_events(month: str = Query(..., pattern=_MONTH_RE), user: str = Depends(require_user)):
    with calendar.connect() as conn:
        return calendar.list_month(conn, user, month)


@router.post("/events")
def create_event(body: EventIn, user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.create_event(conn, user, body)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.patch("/events/{event_id}")
def patch_event(event_id: int, body: EventPatch, user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.update_event(conn, user, event_id, body)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.delete("/events/{event_id}")
def delete_event(event_id: int, user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.delete_event(conn, user, event_id)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
