import time
import os
import sys
from firebase_admin import credentials, initialize_app, storage
from requests import get


initialized_firebase = False


def init_firebase():
    global initialized_firebase
    cred_json = os.path.join(os.path.dirname(sys.argv[0]), "web_tunnel/ip-manager42.json")
    cred = credentials.Certificate(cred_json)
    initialize_app(cred, {'storageBucket': 'ip-manager42.appspot.com'})
    initialized_firebase = True


def upload_ip(ip):
    file_path = os.path.join(os.path.dirname(sys.argv[0]), "ip_server.txt")
    file_name = "ip_server.txt"
    with open(file_path, 'w+') as file:
        file.write(ip)
    bucket = storage.bucket()
    blob = bucket.blob('RaspberryPi-Cyan/' + file_name)
    blob.upload_from_filename(file_path)
    blob.make_public()
    print(f"IP {ip} uploaded to:", blob.public_url)


def read_ip():
    file_name = "ip_server.txt"
    bucket = storage.bucket()
    blob = bucket.blob('RaspberryPi-Cyan/' + file_name)

    if blob.exists():
        ip = blob.download_as_text()
        return ip
    else:
        print("File does not exist in the bucket.")
        return None


# noinspection PyBroadException
def firebase_task(signal, task='upload'):
    global initialized_firebase
    while not signal['kill']:
        for _ in range(10):
            if not signal['kill']:
                time.sleep(0.5)
        try:
            prev_ip = None
            if not initialized_firebase:
                init_firebase()
            while not signal['kill']:
                ip = get('https://api.ipify.org').content.decode('utf8')
                if prev_ip != ip:
                    try:
                        if task == 'upload':
                            upload_ip(ip)
                            prev_ip = ip
                            signal['restart_server'] = True
                        elif task == 'read':
                            ip = read_ip()
                            if signal['server_ip'] != ip:
                                print('Central server ip:', ip)
                            signal['server_ip'] = ip
                    except Exception:
                        print(f'Issue while trying to {task} IP')
                        break
                for _ in range(120):
                    if not signal['kill']:
                        time.sleep(0.5)
        except Exception as e:
            print(f'Issue while trying to {task} IP (initialization)')
            print(e)
            pass
    print('Firebase task terminated.')


if __name__ == '__main__':
    signal = {'kill': False, 'restart_server': False, 'server_ip': None}
    firebase_task(signal, 'read')
