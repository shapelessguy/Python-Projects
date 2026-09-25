#!/usr/bin/env python3
"""certbot's DNS-01 hook for a duckdns.org name: proves the name is ours by
putting certbot's token in its TXT record, through DuckDNS's update API.
Used for LAN_HOST, whose address is on the LAN, so Let's Encrypt cannot
reach it over HTTP the way it does PUBLIC_HOST.

    --manual-auth-hook /hooks/duckdns_hook.py
    --manual-cleanup-hook "/hooks/duckdns_hook.py clean"

certbot passes the name and the token in CERTBOT_DOMAIN and
CERTBOT_VALIDATION; the DuckDNS token is DUCKDNS_TOKEN in secrets.json,
mounted at /cyanhouse/secrets.json (docker-compose.yml).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

SECRETS = "/cyanhouse/secrets.json"
# DuckDNS's servers take a little while to all answer with the new record.
WAIT = 60


def main() -> None:
    clean = sys.argv[1:] == ["clean"]
    token = json.load(open(SECRETS, encoding="utf-8"))["DUCKDNS_TOKEN"]
    domain = os.environ["CERTBOT_DOMAIN"].removesuffix(".duckdns.org")
    query = {"domains": domain, "token": token, "txt": os.environ.get("CERTBOT_VALIDATION", "")}
    if clean:
        query["clear"] = "true"
    url = "https://www.duckdns.org/update?" + urllib.parse.urlencode(query)
    answer = urllib.request.urlopen(url, timeout=30).read().decode().strip()
    if not answer.startswith("OK"):
        sys.exit(f"DuckDNS refused the TXT update for {domain}: {answer}")
    if not clean:
        time.sleep(WAIT)


if __name__ == "__main__":
    main()
