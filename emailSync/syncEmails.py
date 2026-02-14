from __future__ import print_function
import os
import json
import time
import threading
import google_calendar
import outlook
import pythoncom
from datetime import datetime, timezone


PERFORM_OPERATIONS = True


class OpType:
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


class Operation:

    def __init__(self, signal, type_: str, payload, payload2=None):
        self.signal = signal
        self.op_type = type_
        self.payload = payload
        self.payload2 = payload2

    def execute(self):
        if self.op_type == OpType.ADD:
            return google_calendar.add(self.signal, self.payload)
        elif self.op_type == OpType.REMOVE:
            google_calendar.remove(self.signal, self.payload)
        elif self.op_type == OpType.UPDATE:
            google_calendar.update(self.signal, self.payload, self.payload2)


class Signal:
    kill_flag = False
    sync_flag = False
    collections = []
    id_map_path = os.path.join(os.path.dirname(__file__), "id_map.json")

    id_map = {}
    outlook_events = {}
    gmail_events = {}

    def __init__(self):
        self.load_map()
    
    def load_map(self):
        if not os.path.exists(self.id_map_path):
            self.save_map()
        with open(self.id_map_path, "r") as file:
            self.id_map = json.load(file)
    
    def save_map(self):
        with open(self.id_map_path, "w") as file:
            json.dump(self.id_map, file, indent=2)

    def is_alive(self):
        return not self.kill_flag

    def kill(self):
        self.kill_flag = True
    
    def get_events(self):
        self.outlook_events = {}
        self.gmail_events = {}
        try:
            for collection in self.collections:
                for appt in collection:
                    id_, data = outlook.serialize_appt(appt)
                    valid = datetime.fromisoformat(data["start"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
                    if valid:
                        self.outlook_events[id_] = data
            for ev in google_calendar.get_gmail_events(self):
                id_, data = google_calendar.serialize_gmail_ev(ev)
                self.gmail_events[id_] = data
        except Exception:
            import traceback
            print("Exception while getting events:")
            print(traceback.format_exc())
            self.outlook_events = {}
            self.gmail_events = {}
    
    def sync(self):
        if not len(self.outlook_events) or not len(self.gmail_events):
            print(f"At least one element must be already synchronized: len(self.outlook_events)={len(self.outlook_events)}; len(self.gmail_events)={len(self.gmail_events)}")
            return

        print("Synching now...")
        new_map = []
        out_events = {k: v for k, v in self.outlook_events.items()}
        gmail_events = {k: v for k, v in self.gmail_events.items()}
        for out_id, gmail_id in self.id_map:
            if out_id in out_events and gmail_id in gmail_events:
                new_map.append([out_id, gmail_id])
                if out_events[out_id]["hash"] != gmail_events[gmail_id]["hash"]:
                    if PERFORM_OPERATIONS:
                        print(gmail_events[gmail_id])
                        print(out_events[out_id])
                        Operation(self, OpType.UPDATE, gmail_id, out_events[out_id]).execute()
                    pass
            if out_id in out_events:
                del out_events[out_id]
            if gmail_id in gmail_events:
                del gmail_events[gmail_id]

        for _id, data in gmail_events.items():
            if PERFORM_OPERATIONS:
                Operation(self, OpType.REMOVE, _id).execute()
            pass
        for _id, data in out_events.items():
            if PERFORM_OPERATIONS:
                new_map.append([_id, Operation(self, OpType.ADD, data).execute()])
            pass

        self.id_map = new_map
        if PERFORM_OPERATIONS:
            self.save_map()
    
    def cmd_thread(self):
        while self.is_alive():
            try:
                in_ = input()
                if in_ == "last" and len(self.outlook_events):
                    last_event = self.outlook_events[list(self.outlook_events.keys())[-1]]
                    print(json.dumps(last_event, indent=2))
                if in_ == "all" and len(self.outlook_events):
                    for id_, e in self.outlook_events.items():
                        print(id_, json.dumps(e, indent=2))
            except:
                pass
    
    def sync_thread(self):
        pythoncom.CoInitialize()
        outlook.get_outlook_collection(self, 10)
        google_calendar.get_service(self)
        self.get_events()
        self.sync()
        idx = 0
        buffer_n = 40
        prepare_to_sync = False
        print("Detecting updates...")
        while self.is_alive():
            pythoncom.PumpWaitingMessages()
            if self.sync_flag:
                prepare_to_sync = True
                self.sync_flag = False
                idx = 0
            if prepare_to_sync:
                idx += 1
            if idx >= buffer_n:
                self.get_events()
                self.sync()
                idx = 0
                prepare_to_sync = False
            time.sleep(0.1)


def main():
    signal = Signal()
    threading.Thread(target=signal.cmd_thread).start()
    threading.Thread(target=signal.sync_thread).start()
    try:
        while signal.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    signal.kill()


if __name__ == "__main__":
    main()
