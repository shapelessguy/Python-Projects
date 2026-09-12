import time
import requests
import json
import base64
from dotenv import dotenv_values
from PyQt5.QtWidgets import QLineEdit, QTimeEdit
from utils import Parameter, ENV_PATH


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
                params = [x for x in signal.get_threads() if x.name == NAME][0].parameters
                verbose, topic, arg = pending_message
                pending_message = None
                values = {"command": arg}
                if topic == "lights":
                    values["set_auto_time"] = {"from": params.get('Lights from', ''), "to": params.get('Lights to', '')}
                json_content = json.dumps(values)
                
                env_vars = dotenv_values(ENV_PATH)
                username, token = env_vars.get("AUTH", "").split("::")

                host = params.get('Hostname/port', '').rstrip('/')
                url = f"{host}/{topic}"
                creds = f"{username}:{token}"
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': 'Basic ' + base64.b64encode(creds.encode()).decode(),
                }
                if verbose:
                    print("To RoomServer:", url, json_content)
                response = requests.post(url, data=json_content, headers=headers, timeout=5)
                response.encoding = 'iso-8859-1'
                response_text = response.text

                if verbose:
                    print("From RoomServer:", response.status_code, response_text.strip())

            except requests.exceptions.Timeout as ex:
                if verbose:
                    print(f"From RoomServer, Request timed out: {ex}")
            except Exception as ex:
                if verbose:
                    print(f"From RoomServer, HTTP request failed: {ex}")
        time.sleep(0.1)
