import os
from datetime import datetime
import socket
import json
import subprocess


hostnames = {
    'DESKTOP-1FOC71M':{
        'websocket_port': 9999,
        'server_port': 10000,
        'arduino_device': 'COM6'
    },
    'EVA': {
        'websocket_port': 10002,
        'server_port': 10001,
        'arduino_device': None
    },
    'claudio-X200MA': {
        'websocket_port': 10003,
        'server_port': 10004,
        'arduino_device': '/dev/ttyUSB0'
    }
}


HOSTNAME = socket.gethostname()
if HOSTNAME not in hostnames:
    raise Exception('Hostname unkwnown')
HOSTNAME = hostnames[HOSTNAME]

LEO_TOKEN = '6599624331:AAETjn6YXAXVkg4-IV1I_1ip6zchZdmNbUI'
CLAUDIO_ID = 807946519
LEO_GROUP_ID = -4225824414
DUMMY_CHANNEL_ID = -1002037672769


MAIN_FOLDER_PATH = os.path.dirname(__file__)

BOT_AI_PATH = os.path.join(MAIN_FOLDER_PATH, 'bot_ai')
WG_PATH = os.path.join(MAIN_FOLDER_PATH, 'wg')
DATA_PATH = os.path.join(WG_PATH, 'data')
ALL_WG_LOGS_PATH = os.path.join(DATA_PATH, 'all_wg_logs')
LOG_FILE_PATH = os.path.join(MAIN_FOLDER_PATH, "logs")

MSG_HISTORY_PATH = os.path.join(BOT_AI_PATH, 'history.json')

BLAME_LOGS_FILEPATH = os.path.join(ALL_WG_LOGS_PATH, 'blame_log.json')
WARN_LOGS_FILEPATH = os.path.join(ALL_WG_LOGS_PATH, 'warn_log.json')
ANNOUNCEMENT_FILEPATH = os.path.join(ALL_WG_LOGS_PATH, 'announcements.txt')
LAST_IDX_FILEPATH = os.path.join(ALL_WG_LOGS_PATH, 'last_idx_reads.json')
FINANCE_EXCEL_FILEPATH = os.path.join(ALL_WG_LOGS_PATH, "expenses.xlsx")

STOCK_DB_PATH = os.path.join(MAIN_FOLDER_PATH, 'stock_data')


for folder in [WG_PATH, LOG_FILE_PATH, DATA_PATH, ALL_WG_LOGS_PATH]:
    if not os.path.exists(folder):
        os.mkdir(folder)

for json_ in [BLAME_LOGS_FILEPATH, WARN_LOGS_FILEPATH, LAST_IDX_FILEPATH]:
    if not os.path.exists(json_):
        with open(json_, 'w') as file:
            json.dump({}, file)


def pull(path, signal):
    print(f"Pulling from GitHub: {path}")
    r = subprocess.run(f'cd {path} && git pull', shell=True, capture_output=True, text=True)
    print(r.stdout)
    print(r.stderr)
    if  r.returncode != 0:
        signal['kill'] = True
        return False
    return True


def push(path, signal):
    print(f"Pushing to GitHub: {path}")
    r = subprocess.run(f'cd {path} && git add . && git commit -m "auto_update" && git push', shell=True, capture_output=True, text=True)
    print(r.stdout)
    print(r.stderr)
    if r.returncode != 0:
        signal['kill'] = True
        return False
    return True


class TeeOutput:
    def __init__(self, name, sys_out, log_file_name):
        self.name = name
        log_file = open(os.path.join(LOG_FILE_PATH, log_file_name), "a", encoding='utf-8')
        self.streams = [sys_out, log_file]

    def write(self, message):
        self.streams[0].write(message)
        self.streams[0].flush()
        message = '\n'.join([f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}][{self.name}] - {m}\n" for m in message.split('\n') if m.strip() != ''])
        try:
            self.streams[1].write(message)
            self.streams[1].flush()
        except UnicodeEncodeError:
            encoded_message = message.encode('utf-8', 'replace').decode('utf-8')
            self.streams[1].write(encoded_message)
            self.streams[1].flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()
