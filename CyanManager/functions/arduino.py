import requests
import json
from utils import pprint


def get_roomserver_settings(signal, verbose, topic, arg):
    try:
        values = {topic: arg}
        json_content = json.dumps(values)
        url = f"http://cyanroomserver.duckdns.org:{signal.get_roomserver_settings()['port']}/{topic}"
        response = requests.post(url, data=json_content, headers={'Content-Type': 'application/json'}, timeout=5)
        response.encoding = 'iso-8859-1'
        response_text = response.text

        if verbose:
            pprint(response_text.strip())
        return True

    except requests.exceptions.Timeout as ex:
        if verbose:
            pprint(f"Request timed out: {ex}")
        return False
    except Exception as ex:
        if verbose:
            pprint(f"HTTP request failed: {ex}")
        return False


def lights_on(signal, verbose=False):
    get_roomserver_settings(signal, verbose, "lights", "on")


def lights_off(signal, verbose=False):
    get_roomserver_settings(signal, verbose, "lights", "off")


def lights_auto(signal, verbose=False):
    get_roomserver_settings(signal, verbose, "lights", "auto")
