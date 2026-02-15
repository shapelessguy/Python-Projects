from __future__ import print_function
import datetime
import os.path
import pickle
import json
from dotenv import dotenv_values, load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from utils import hash_str, normalize_to_utc
work_calendar_id = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))['CALENDAR_ID']


category_map = {
    "": "",
    "BECCAL": "3",
    "IDEA": "6",
    "Important": "11",
    "MBSE4GK": "2",
    "SENSE-RAI": "5",
}


def get_service(signal):
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None
    if os.path.exists(os.path.join(os.path.dirname(__file__), 'token.pickle')):
        with open(os.path.join(os.path.dirname(__file__), 'token.pickle'), 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(os.path.join(os.path.dirname(__file__), 'credentials.json'), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(os.path.join(os.path.dirname(__file__), 'token.pickle'), 'wb') as token:
            pickle.dump(creds, token)
    signal.service = build('calendar', 'v3', credentials=creds)


def serialize_gmail_ev(item):
    data = {
        # Identity
        # "entry_id": item.get("id", ""),
        # "etag": item.get("etag", ""),

        # Core info
        "subject": item.get("summary", ""),
        "location": item.get("location", ""),
        "start": normalize_to_utc(item.get("start", {'dateTime': ''})["dateTime"]),
        "end": normalize_to_utc(item.get("end", {'dateTime': ''})["dateTime"]),
        "category": next((k for k, v in category_map.items() if v == item.get("colorId", "")), "")

        # Metadata
        # "created": item.get("created", ""),
        # "modified": item.get("updated", ""),
    }
    data["hash"] = hash_str(json.dumps(data))
    return item["id"], data


def to_gmail_event(data):
    body = {
        "summary": data.get("subject"),
        "location": data.get("location"),
        "start": {"dateTime": data["start"], "timeZone": "UTC"},
        "end": {"dateTime": data["end"], "timeZone": "UTC"},
    }
    if data["category"] != "":
        body["colorId"] = category_map.get(data["category"], "")
    return body


def get_gmail_events(signal):
    from_ = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).isoformat().replace('+00:00', 'Z')
    events_result = signal.service.events().list(calendarId=work_calendar_id, timeMin=from_, maxResults=999999,
                                          singleEvents=True, orderBy='startTime').execute()
    events = events_result.get('items', [])
    final = []
    for ev in events:
        final.append(ev)
    return final


def add(signal, data):
    created = signal.service.events().insert(calendarId=work_calendar_id, body=to_gmail_event(data)).execute()
    print("Created:", created["id"], created["start"]["dateTime"])
    return created["id"]


def remove(signal, event_id):
    print("Removed:", event_id)
    signal.service.events().delete(calendarId=work_calendar_id, eventId=event_id).execute()


def update(signal, event_id, data):
    print("Updated:", event_id)
    signal.service.events().update(calendarId=work_calendar_id, eventId=event_id, body=to_gmail_event(data)).execute()
