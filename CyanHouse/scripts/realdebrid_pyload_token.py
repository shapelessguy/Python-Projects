#!/usr/bin/env python3
"""Authorise pyLoad with Real-Debrid.

pyLoad-ng's RealdebridCom account doesn't take the private API key from
real-debrid.com/apitoken. It wants OAuth device credentials: username
"<client_id>/<client_secret>" and password = a refresh token, which it then
trades for short-lived API tokens by itself (see RealdebridCom.signin in the
container). This runs Real-Debrid's device flow — the same thing pyLoad's
GetRealdebridToken.py does — and prints the two values to paste into
Downloads → Settings → Accounts → RealdebridCom.

    python3 scripts/realdebrid_pyload_token.py
"""
import json
import urllib.error
import time
import urllib.parse
import urllib.request

API = "https://api.real-debrid.com/oauth/v2"
# Real-Debrid's public client id for open-source apps; the device flow below
# swaps it for a client id/secret of your own.
OPENSOURCE_CLIENT_ID = "X245A4XAIBGVM"


def get(path: str, **params) -> dict:
    with urllib.request.urlopen(f"{API}{path}?{urllib.parse.urlencode(params)}") as r:
        return json.load(r)


def post(path: str, **data) -> dict:
    body = urllib.parse.urlencode(data).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{API}{path}", data=body)) as r:
        return json.load(r)


def main() -> None:
    dev = get("/device/code", client_id=OPENSOURCE_CLIENT_ID, new_credentials="yes")
    print(f"1. Open {dev['verification_url']} (signed in to Real-Debrid)")
    print(f"2. Enter the code:  {dev['user_code']}")
    print("Waiting for you to approve it…")

    deadline = time.time() + dev["expires_in"]
    creds = {}
    while time.time() < deadline:
        time.sleep(dev.get("interval", 5))
        try:
            creds = get("/device/credentials", client_id=OPENSOURCE_CLIENT_ID, code=dev["device_code"])
        except urllib.error.HTTPError:
            continue  # not approved yet
        if "client_secret" in creds:
            break
    else:
        raise SystemExit("Timed out — run it again.")

    token = post("/token", client_id=creds["client_id"], client_secret=creds["client_secret"],
                 code=dev["device_code"], grant_type="http://oauth.net/grant_type/device/1.0")

    print("\nIn Downloads → Settings → Accounts, add a RealdebridCom account with:")
    print(f"  Username:  {creds['client_id']}/{creds['client_secret']}")
    print(f"  Password:  {token['refresh_token']}")


if __name__ == "__main__":
    main()
