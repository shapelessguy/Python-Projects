import traceback
import sys
import ctypes
from queue import Queue
from gui.manage_ui import UI_Manager
from gui.db_api import MongoDB
from utils import Tee, pprint


class Signal:
    kill_flag = False
    ui_manager = None
    cur_review: str
    cur_library: str
    mongo: MongoDB = None

    def __init__(self):
        self.log_queue = Queue()

        sys.stdout = Tee(self.log_queue, sys.stdout)
        sys.stderr = Tee(self.log_queue, sys.stderr)
        self.threads = {}
        self.session_locked = False
        self.kill_flag = False
        self.mongo = MongoDB("localhost", 8001)
        self.mongo.connect()
    
    def set_current_review(self, review):
        self.cur_review = review
    
    def set_current_library(self, library):
        self.cur_library = library
    
    def fetch_containers(self):
        return self.mongo.fetch_containers(self.cur_review)
    
    def kill(self):
        self.kill_flag = True
    
    def is_alive(self):
        return not self.kill_flag


def main():
    sys.argv.append('--no-sandbox')
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LiteratureEngine")
    
    form_closed = 1
    signal = None
    try:
        signal = Signal()
        signal.ui_manager = UI_Manager(signal)
        signal.ui_manager.start_gui_tasks()

        form_closed = signal.ui_manager.execute("wait_for_close")
    except Exception:
        pprint(traceback.format_exc())
    except KeyboardInterrupt:
        pass
    if signal:
        signal.kill()

    pprint("LiteratureEngine terminated")
    if form_closed == 1:
        sys.exit()
    else:
        sys.exit(form_closed)


if __name__ == "__main__":
    main()
