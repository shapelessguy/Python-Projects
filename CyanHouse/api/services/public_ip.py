"""Keeping the outside world pointed at the home connection.

The home IP changes now and then. Two things have to follow it:

- the DuckDNS name (PUBLIC_HOST), which is how CyanHouse, Plex and the rest
  are reached from outside;
- the address Plex hands its apps. Plex would normally work that out by
  itself, but it asks plex.tv, and this machine's traffic leaves through
  NordVPN — so plex.tv sees the VPN's address and sends the apps there. It
  is given the real address instead (see plex.set_public_address).

The address is asked of the router over UPnP (GetExternalIPAddress) rather
than of an "what is my IP" site, for the same reason: any site would see the
VPN. Nothing is changed when the router cannot be asked — better to leave an
address as it is than to replace it with a wrong one.

Carried over from RoomServer's trackIp_utils.py, which did the DuckDNS half
by asking api.ipify.org — fine on a machine without a VPN, not on this one.
"""
import re
import threading
import time

import requests

from api.config import DUCKDNS_DOMAIN, DUCKDNS_TOKEN, PUBLIC_IP_INTERVAL, ROUTER_UPNP_URL
from api.services import plex

_SOAP = (
    '<?xml version="1.0"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
    '<u:GetExternalIPAddress xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1"/>'
    '</s:Body></s:Envelope>'
)
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

_lock = threading.Lock()
_started = False
# What was last pushed where, so each is only told when the address moves.
_state: dict = {"ip": None, "duckdns": None, "plex": None, "checked": None, "error": ""}


def router_ip() -> str:
    """The home connection's public IPv4, as the router has it."""
    r = requests.post(
        ROUTER_UPNP_URL + "/igdupnp/control/WANIPConn1",
        data=_SOAP,
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SoapAction": "urn:schemas-upnp-org:service:WANIPConnection:1#GetExternalIPAddress",
        },
        timeout=10,
    )
    r.raise_for_status()
    m = re.search(r"<NewExternalIPAddress>([^<]*)</NewExternalIPAddress>", r.text)
    ip = (m.group(1) if m else "").strip()
    # A router still dialling in answers 0.0.0.0 or nothing at all.
    if not _IPV4.match(ip) or ip.startswith("0."):
        raise RuntimeError(f"the router has no public address right now ({ip or 'empty'})")
    return ip


def update_duckdns(ip: str) -> None:
    """Point the DuckDNS name at `ip`. The address is passed explicitly:
    left out, DuckDNS would take it from the request — the VPN's again."""
    r = requests.get("https://www.duckdns.org/update",
                     params={"domains": DUCKDNS_DOMAIN, "token": DUCKDNS_TOKEN, "ip": ip},
                     timeout=15)
    r.raise_for_status()
    if r.text.strip() != "OK":
        raise RuntimeError(f"DuckDNS refused the update ({r.text.strip() or 'no answer'})")


def check() -> dict:
    """Ask the router once and bring DuckDNS and Plex up to date."""
    problems = []
    try:
        ip = router_ip()
    except Exception as e:
        problems.append(f"router: {e}")
        ip = None
    if ip:
        if ip != _state["ip"]:
            print(f"public_ip: home address is {ip}")
            _state["ip"] = ip
        if DUCKDNS_TOKEN and DUCKDNS_DOMAIN and _state["duckdns"] != ip:
            try:
                update_duckdns(ip)
                _state["duckdns"] = ip
                print(f"public_ip: {DUCKDNS_DOMAIN}.duckdns.org -> {ip}")
            except Exception as e:
                problems.append(f"duckdns: {e}")
        if _state["plex"] != ip:
            try:
                url = plex.set_public_address(ip)
                _state["plex"] = ip
                if url:
                    print(f"public_ip: Plex now tells its apps {url}")
            except Exception as e:
                problems.append(f"plex: {e}")
    error = "; ".join(problems)
    # Said once, not every minute for as long as it lasts.
    if error and error != _state["error"]:
        print(f"public_ip: {error}")
    _state["error"] = error
    _state["checked"] = time.time()
    return dict(_state)


def status() -> dict:
    return dict(_state)


def _loop() -> None:
    while True:
        try:
            check()
        except Exception as e:  # never let the thread die
            print(f"public_ip: {e.__class__.__name__}: {e}")
        time.sleep(max(15, PUBLIC_IP_INTERVAL))


def start() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="public-ip", daemon=True).start()
