"""Calendar — personal + shared events, entirely local (no external account).
Every event belongs to a calendar: a user's own (starting with an
auto-created "Default", plus any they name themselves) are visible only to
them until they share one, person by person, to see, edit or manage it. Self-contained module: own DB, own version counter — see
api/services/calendar.py and food.py's router for the template this follows.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api.auth import require_user
from api.models import CalendarIn, CalendarPatch, EventIn, EventPatch
from api.services import calendar

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

VERSION_NAMES = ["calendar"]
PANEL = "calendar"  # gates the whole router behind permissions.visibility -- see api/auth.py

_MONTH_RE = r"^\d{4}-\d{2}$"
_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


def init() -> None:
    calendar.init_db()


def versions(user: str | None) -> dict[str, int]:
    with calendar.connect() as conn:
        return {"calendar": calendar.version(conn)}


@router.get("/calendars")
def get_calendars(user: str = Depends(require_user)):
    with calendar.connect() as conn:
        return calendar.list_calendars(conn, user)


@router.post("/calendars")
def create_calendar(body: CalendarIn, user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.create_calendar(conn, user, body.name, body.color, body.shared)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.patch("/calendars/{calendar_id}")
def patch_calendar(calendar_id: int, body: CalendarPatch, user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.update_calendar(conn, user, calendar_id, body.name, body.color, body.shared)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/calendars/sharing/users")
def sharing_users(_user: str = Depends(require_user)):
    """Who a calendar can be shared with."""
    return calendar.sharing_users()


@router.put("/calendars/{calendar_id}/sharing")
def put_sharing(calendar_id: int, body: dict = Body(...), user: str = Depends(require_user)):
    """Who else sees a calendar: {"people": {"<user>": "see"|"edit"|"manage"}};
    empty is private. For its owner and whoever may manage it."""
    try:
        with calendar.connect() as conn:
            return calendar.set_sharing(conn, user, calendar_id, body.get("people") or {})
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.delete("/calendars/{calendar_id}")
def delete_calendar(calendar_id: int, user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.delete_calendar(conn, user, calendar_id)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


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


# Declared ahead of /events/{event_id} (a static path segment could otherwise
# be swallowed by a dynamic one matched first, depending on route order).
@router.post("/events/bulk")
def create_events_bulk(body: list[EventIn], user: str = Depends(require_user)):
    try:
        with calendar.connect() as conn:
            return calendar.create_events_bulk(conn, user, body)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.delete("/events")
def delete_events_from(
    from_date: str = Query(..., pattern=_DATE_RE),
    calendar_id: int | None = Query(None),
    user: str = Depends(require_user),
):
    try:
        with calendar.connect() as conn:
            return {"deleted": calendar.delete_events_from(conn, user, from_date, calendar_id)}
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
def delete_event(
    event_id: int,
    occurrence: str | None = Query(None, pattern=_DATE_RE),
    user: str = Depends(require_user),
):
    try:
        with calendar.connect() as conn:
            return calendar.delete_event(conn, user, event_id, occurrence)
    except calendar.CalendarError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
