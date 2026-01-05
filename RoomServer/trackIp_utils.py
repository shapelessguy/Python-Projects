import time
import requests
import socket
from utils import HOSTNAME, DUCKDNS_TOKEN


def get_duckdns_ip():
    hostname = f"{HOSTNAME['domain']}.duckdns.org"
    return socket.gethostbyname(hostname)


def update_duckdns(signal, ip):
    url = "https://www.duckdns.org/update"
    params = {
        "domains": HOSTNAME['domain'],
        "token": DUCKDNS_TOKEN,
        "verbose": "true",
        "ip": ip
    }

    try:
        output = [l for l in requests.get(url, params=params).text.split("\n") if l != ""]
        status = output[0]
        updated_ip = output[1]
        msg = "\n".join(output[2:])
        if status == "OK":
            print(f"Upload IP successful: {msg}. New IP: {ip}")
        else:
            print(f"Error while uploading the ip: {msg}")
            return None
        while not signal['kill']:
            time.sleep(1)
            current_ip = get_duckdns_ip()
            if current_ip == updated_ip:
                return current_ip
    except Exception as e:
        print(f"Error while updating duckdns: {e}")
    return None


# noinspection PyBroadException
def trackIp_task(signal):
    while not signal['kill']:
        for _ in range(10):
            if not signal['kill']:
                time.sleep(0.5)
        try:
            prev_ip = get_duckdns_ip()
            while not signal['kill']:
                ip = requests.get('https://api.ipify.org').content.decode('utf8')
                if prev_ip != ip:
                    try:
                        update_duckdns(signal, ip)
                        prev_ip = ip
                        signal['restart_server'] = True
                        signal['restart_websocket'] = True
                    except Exception:
                        print('Issue while trying to upload IP')
                        break
                for _ in range(120):
                    if not signal['kill']:
                        time.sleep(0.5)
        except Exception as e:
            print('Issue while trying to upload IP (initialization)')
            print(e)
            pass
    print('TrackIP task terminated.')


if __name__ == '__main__':
    trackIp_task({'kill': False})
