from __future__ import print_function
import base64
import json
import os
from datetime import datetime, timedelta, timezone
import requests
from dotenv import dotenv_values

_env = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))
CYAN_SERVER = _env["CYANSERVER"]
CYAN_USER = _env["CYANUSER"]
CYAN_TOKEN = _env["CYANTOKEN"]
CYAN_CALENDAR_NAME = "DLR"

BASE_URL = f"https://{CYAN_SERVER}"


def _session():
    session = requests.Session()
    raw = f"{CYAN_USER}:{CYAN_TOKEN}".encode("utf-8")
    session.headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    return session


def _get_or_create_calendar_id(session):
    resp = session.get(f"{BASE_URL}/api/calendar/calendars", timeout=15)
    resp.raise_for_status()
    calendars = resp.json()
    for cal in calendars:
        if cal["name"] == CYAN_CALENDAR_NAME:
            return cal["id"]

    resp = session.post(f"{BASE_URL}/api/calendar/calendars", json={"name": CYAN_CALENDAR_NAME}, timeout=15)
    resp.raise_for_status()
    for cal in resp.json():
        if cal["name"] == CYAN_CALENDAR_NAME:
            return cal["id"]
    raise RuntimeError(f"Failed to create or find calendar {CYAN_CALENDAR_NAME!r}")


def _split_iso(ts):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _bump_zero_duration(start_time, end_time):
    """CyanHouse rejects a same-day event whose end_time isn't after its
    start_time. Outlook sometimes reports zero-duration appointments (start
    == end, e.g. a reminder-only entry) -- give those a minimal 15-minute
    span instead of failing the whole bulk insert."""
    start_dt = datetime.strptime(start_time, "%H:%M")
    end_dt = datetime.strptime(end_time, "%H:%M")
    if end_dt <= start_dt:
        end_dt = min(start_dt + timedelta(minutes=15), start_dt.replace(hour=23, minute=59))
    return end_dt.strftime("%H:%M")


def _build_description(data):
    parts = []
    location = (data.get("location") or "").strip()
    if location:
        parts.append(f"Loc: {location}")
    category = (data.get("category") or "").strip()
    if category:
        parts.append(f"Category: {category}")
    body = (data.get("body") or "").strip()
    if body:
        parts.append(body)
    return "\n".join(parts)


def to_cyan_event(data, calendar_id):
    start_date, start_time = _split_iso(data["start"])
    end_date, end_time = _split_iso(data["end"])
    if start_date == end_date:
        end_time = _bump_zero_duration(start_time, end_time)
    return {
        "title": data.get("subject") or "(no title)",
        "description": _build_description(data),
        "start_date": start_date,
        "end_date": end_date,
        "all_day": False,
        "start_time": start_time,
        "end_time": end_time,
        "calendar_id": calendar_id,
    }


def sync_events(outlook_events):
    session = _session()
    calendar_id = _get_or_create_calendar_id(session)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    del_resp = session.delete(
        f"{BASE_URL}/api/calendar/events",
        params={"from_date": today, "calendar_id": calendar_id},
        timeout=15,
    )
    del_resp.raise_for_status()
    print("Deleted from CyanHouse:", del_resp.json().get("deleted"))

    events = [to_cyan_event(data, calendar_id) for data in outlook_events.values()]
    if events:
        ins_resp = session.post(f"{BASE_URL}/api/calendar/events/bulk", json=events, timeout=15)
        if not ins_resp.ok:
            print(f"Bulk insert failed ({ins_resp.status_code}): {ins_resp.text}")
            for i, ev in enumerate(events):
                print(f"  [{i}]", json.dumps(ev))
        ins_resp.raise_for_status()
        print("Inserted into CyanHouse:", len(events))
    else:
        print("No Outlook events to insert.")
