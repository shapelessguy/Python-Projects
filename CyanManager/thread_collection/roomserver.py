import time
import requests
import json
from PyQt5.QtWidgets import QLineEdit, QTimeEdit
from utils import Parameter


NAME = "Roomserver"
PARAMETERS = {
    "Hostname/port": Parameter("", QLineEdit),
    "Lights from": Parameter("09:00", QTimeEdit),
    "Lights to": Parameter("20:00", QTimeEdit),
}


def send_to_roomserver(signal, verbose, topic, arg):
    global pending_message
    pending_message = verbose, topic, arg


def entrypoint(thread_manager):
    global pending_message
    pending_message = None
    signal = thread_manager.signal
    while thread_manager.signal.is_alive() and not thread_manager.to_kill:
        if pending_message:
            try:
                verbose, topic, arg = pending_message
                pending_message = None
                values = {topic: arg}
                json_content = json.dumps(values)
                params = [x for x in signal.get_threads() if x.name == NAME][0].parameters
                url = f"{params.get('Hostname/port', '')}/{topic}"
                response = requests.post(url, data=json_content, headers={'Content-Type': 'application/json'}, timeout=5)
                response.encoding = 'iso-8859-1'
                response_text = response.text

                if verbose:
                    print("From RoomServer:", response_text.strip())

            except requests.exceptions.Timeout as ex:
                if verbose:
                    print(f"From RoomServer, Request timed out: {ex}")
            except Exception as ex:
                if verbose:
                    print(f"From RoomServer, HTTP request failed: {ex}")
        time.sleep(0.1)
