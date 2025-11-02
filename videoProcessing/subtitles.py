import requests
import os
import json


login_url = "https://api.opensubtitles.com/api/v1/login"
secrets_path = os.path.join(os.path.dirname(__file__), ".api.json")
init_keys = {'api_token': None, 'username': None, 'password': None, 'bearer': None}
APP_NAME = "autoSub"


with open(secrets_path, "r") as f:
    keys = {**init_keys, **json.loads(f.read())}
    API_KEY = keys['api_token']
    USERNAME = keys['username']
    PASSWORD = keys['password']
    BEARER = keys['bearer']


def login():
    headers = {
        "Content-Type": "application/json",
        "Api-Key": API_KEY,
        "User-Agent": APP_NAME
    }
    payload = {
        "username": "shapelessguy",
        "password": "Oo180393acer"
    }

    response = requests.post(login_url, headers=headers, json=payload)

    if response.ok:
        data = response.json()
        bearer_token = data.get("token")
        keys['bearer'] = bearer_token
        with open(secrets_path, "w") as f:
            json.dump(keys, f, indent=4)
        print("✅ Login successful!")
    else:
        print("❌ Login failed:", response.status_code, response.text)


def connection_check():
    headers = {
        "Content-Type": "application/json",
        # "Api-Key": API_KEY,
        # "User-Agent": APP_NAME,
        # "Authorization": f"Bearer {keys['bearer']}"
    }

    url = "https://api.opensubtitles.com/api/v1/subtitles"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print("✅ Token is valid!")
    elif response.status_code == 401:
        print("❌ Token is invalid or expired!")
    else:
        print(response)
        print(f"⚠️ Unexpected status code: {response.status_code}")


# login()
connection_check()
