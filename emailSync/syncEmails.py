from __future__ import print_function
import json
import time
import threading
import cyan_calendar
import outlook
import pythoncom
from datetime import datetime, timezone


PERFORM_OPERATIONS = True
SYNC_AFTER = 120  # Synchronization after N seconds of inactivity


class Signal:
    kill_flag = False
    sync_flag = False
    collections = []
    last_sync = time.time()

    outlook_events = {}

    def is_alive(self):
        return not self.kill_flag

    def kill(self):
        self.kill_flag = True

    def get_events(self):
        self.outlook_events = {}
        try:
            for collection in self.collections:
                for appt in collection:
                    id_, data = outlook.serialize_appt(appt)
                    start_date = datetime.fromisoformat(data["start"].replace("Z", "+00:00")).date()
                    valid = start_date >= datetime.now(timezone.utc).date()
                    if valid:
                        self.outlook_events[id_] = data
        except Exception:
            import traceback
            print("Exception while getting events:")
            print(traceback.format_exc())
            self.outlook_events = {}

    def sync(self):
        if not len(self.outlook_events):
            print("No Outlook events collected; skipping sync.")
            return

        print("Synchronizing now...")
        if PERFORM_OPERATIONS:
            try:
                cyan_calendar.sync_events(self.outlook_events)
            except Exception:
                import traceback
                print("Exception while syncing to CyanHouse:")
                print(traceback.format_exc())
        self.last_sync = time.time()

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
        self.get_events()
        self.sync()
        idx = 0
        buffer_n = 40
        prepare_to_sync = False
        print("Detecting updates...")
        while self.is_alive():
            pythoncom.PumpWaitingMessages()
            now = time.time()
            if self.sync_flag:
                prepare_to_sync = True
                self.sync_flag = False
                idx = 0
            if prepare_to_sync:
                idx += 1
            if idx >= buffer_n or now - self.last_sync > SYNC_AFTER:
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
