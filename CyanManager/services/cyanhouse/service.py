import base64
import time
import requests
import json
import api_auth


NAME = "CyanHouse"
PARAMETERS = {}


def send_to_cyanhouse(signal, verbose, topic, arg):
    global pending_message
    pending_message = verbose, topic, arg


def request_cyanhouse(topic, arg, verbose=False, timeout=5):
    # The lights' auto window is set in CyanHouse itself: "auto" reuses the last one saved there.
    json_content = json.dumps({"command": arg})

    # CyanHouse's Room actuator, at CYANHOUSE_URL, as INSTANCE_ID / INSTANCE_TOKEN (.env).
    username, token = api_auth.own_credentials() or ("", "")

    url = f"{api_auth.cyanhouse_url()}/api/controls/room/{topic}"
    creds = f"{username}:{token}"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Basic ' + base64.b64encode(creds.encode()).decode(),
    }
    if verbose:
        print("To CyanHouse:", url, json_content)
    response = requests.post(url, data=json_content, headers=headers, timeout=timeout)
    response.encoding = 'iso-8859-1'
    response_text = response.text

    if verbose:
        print("From CyanHouse:", response.status_code, response_text.strip())


def entrypoint(thread_manager):
    global pending_message
    pending_message = None
    while thread_manager.signal.is_alive() and not thread_manager.to_kill:
        if pending_message:
            try:
                verbose, topic, arg = pending_message
                pending_message = None
                request_cyanhouse(topic, arg, verbose)

            except requests.exceptions.Timeout as ex:
                if verbose:
                    print(f"From CyanHouse, Request timed out: {ex}")
            except Exception as ex:
                if verbose:
                    print(f"From CyanHouse, HTTP request failed: {ex}")
        time.sleep(0.1)
