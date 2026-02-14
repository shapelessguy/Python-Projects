from __future__ import print_function
import json
import win32com.client
import datetime
from datetime import timedelta
from utils import hash_str


def outlook_time(dt):
    dt_utc = datetime.datetime.fromisoformat(str(dt)) - timedelta(hours=1)
    return dt_utc.isoformat().replace("+00:00", "Z")


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def serialize_appt(item):
    data = {
        # Identity
        # "entry_id": safe_get(item, "EntryID"),
        # "global_id": safe_get(item, "GlobalAppointmentID"),

        # Core info
        "subject": safe_get(item, "Subject"),
        "location": safe_get(item, "Location"),
        "start": outlook_time(safe_get(item, "Start")),
        "end": outlook_time(safe_get(item, "End")),
        # "all_day": safe_get(item, "AllDayEvent"),

        # # Metadata
        # "created": outlook_time(safe_get(item, "CreationTime")),
        # "modified": outlook_time(safe_get(item, "LastModificationTime")),
        # "organizer": safe_get(item, "Organizer"),
        "category": safe_get(item, "Categories").split(", ")[0],

        # # Flags / status
        # "is_recurring": safe_get(item, "IsRecurring"),
        # "busy_status": safe_get(item, "BusyStatus"),
        # "sensitivity": safe_get(item, "Sensitivity"),
        # "meeting_status": safe_get(item, "MeetingStatus"),
        # "response_status": safe_get(item, "ResponseStatus"),
        # "reminder_set": safe_get(item, "ReminderSet"),
        # "reminder_minutes": safe_get(item, "ReminderMinutesBeforeStart"),
        # "required_attendees": safe_get(item, "RequiredAttendees"),
        # "optional_attendees": safe_get(item, "OptionalAttendees"),
    }
    data["hash"] = hash_str(json.dumps(data))
    return data["hash"], data


class CalendarEvents:
    signal = None

    def OnItemAdd(self, item):
        self.signal.sync_flag = True

    def OnItemChange(self, item):
        self.signal.sync_flag = True

    def OnItemRemove(self):
        self.signal.sync_flag = True


def get_restriction(start_filter, end_filter):
    return f"[Start] >= '{start_filter.strftime('%m/%d/%Y')} 00:00' AND [End] <= '{end_filter.strftime('%m/%d/%Y')} 23:59'"


def get_outlook_collection(signal, n_weeks):
    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    calendar = outlook.GetDefaultFolder(9)

    items = calendar.Items
    items.Sort("[Start]")
    items.IncludeRecurrences = True

    for i in range(0, n_weeks):
        start_filter = datetime.datetime.now() + datetime.timedelta(days=7 * i)
        end_filter = datetime.datetime.now() + datetime.timedelta(days=7 * (i+1))
        signal.collections.append(items.Restrict(get_restriction(start_filter, end_filter)))
    
    signal.handlers = []
    signal.handlers.append(win32com.client.WithEvents(signal.collections[0], CalendarEvents))
    signal.handlers[-1].signal = signal
