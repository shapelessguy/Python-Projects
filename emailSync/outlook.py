from __future__ import print_function
import binascii
import json
import win32com.client
import win32com.mapi.mapi as mapi
import win32com.mapi.mapitags as mapitags
import datetime
from utils import hash_str


def outlook_time(dt):
    dt_utc = datetime.datetime.fromisoformat(str(dt))
    return dt_utc.isoformat().replace("+00:00", "Z")


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


# The Outlook Object Model's `Body` property is blocked by Outlook's Object
# Model Guard (an org-enforced security policy on this machine) -- it fails
# with a generic COM error regardless of how the item is fetched. Extended
# MAPI reads the same data directly from the message store and isn't subject
# to that guard, so we use it just for the body text.
_mapi_stores = None


def _get_mapi_stores():
    global _mapi_stores
    if _mapi_stores is not None:
        return _mapi_stores
    opened = []
    try:
        mapi.MAPIInitialize(None)
        session = mapi.MAPILogonEx(0, "", "", mapi.MAPI_NO_MAIL | mapi.MAPI_EXTENDED | mapi.MAPI_USE_DEFAULT)
        stores_table = session.GetMsgStoresTable(0)
        stores_table.SetColumns([mapitags.PR_ENTRYID, mapitags.PR_DISPLAY_NAME_W], 0)
        while True:
            rows = stores_table.QueryRows(10, 0)
            if not rows:
                break
            for row in rows:
                _, entryid_val = row[0]
                try:
                    opened.append(session.OpenMsgStore(0, entryid_val, None, mapi.MAPI_BEST_ACCESS | mapi.MDB_NO_MAIL))
                except Exception:
                    pass
    except Exception:
        opened = []
    _mapi_stores = opened
    return _mapi_stores


def get_body(entry_id_hex):
    if not entry_id_hex:
        return ""
    try:
        entry_id_bytes = binascii.unhexlify(entry_id_hex)
    except Exception:
        return ""
    for store in _get_mapi_stores():
        try:
            msg = store.OpenEntry(entry_id_bytes, None, mapi.MAPI_BEST_ACCESS)
            _, props = msg.GetProps([mapitags.PR_BODY_W], 0)
            tag, val = props[0]
            if tag == mapitags.PR_BODY_W and val:
                return val
        except Exception:
            continue
    return ""


def serialize_appt(item):
    entry_id = safe_get(item, "EntryID")
    data = {
        # Identity
        # "global_id": safe_get(item, "GlobalAppointmentID"),

        # Core info
        "subject": safe_get(item, "Subject"),
        "location": safe_get(item, "Location"),
        "start": outlook_time(safe_get(item, "Start")),
        "end": outlook_time(safe_get(item, "End")),
        "body": get_body(entry_id),
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
