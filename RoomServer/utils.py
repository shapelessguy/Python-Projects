import os
from datetime import datetime
import socket

hostnames = {
    'DESKTOP-1FOC71M':{
        'websocket_port': 9999,
        'server_port': 10000,
        'arduino_device': 'COM6'
    },
    'raspberrypi': {
        'websocket_port': 10002,
        'server_port': 10001,
        'arduino_device': '/dev/ttyUSB0'
    },
    'EVA': {
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
BLAME_LOGS_FILEPATH = os.path.join(os.path.dirname(__file__), 'blame_log.json')
BLAMES_FILEPATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'WG', 'blames.json')


log_file_path = os.path.join(os.path.dirname(__file__), "output.log")
log_file = open(log_file_path, "a", encoding='utf-8')


class TeeOutput:
    def __init__(self, sys_out):
        self.streams = [sys_out, log_file]

    def write(self, message):
        self.streams[0].write(message)
        self.streams[0].flush()
        message = '\n'.join([f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] - {m}\n" for m in message.split('\n') if m.strip() != ''])
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
