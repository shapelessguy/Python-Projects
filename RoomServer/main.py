from server import server_control
from websocket import websocket_control
from actuators import launch_actuator
from firebase_utils import firebase_task
from utils import TeeOutput
from datetime import datetime
import multiprocessing
import threading
import sys
import os
import time
import json


RESET_HOUR = 4  # At this hour, the server will restart


def background(signal):
    pass


class State:
    def __init__(self):
        self.main_path = os.path.dirname(__file__)
        self.path = os.path.join(self.main_path, 'state.json')
        self.state = {'audio': False}
        if os.path.exists(self.path):
            with open(self.path, 'r') as file:
                self.state = json.load(file)
        print(self.state)
    
    def get_param(self, param):
        output = None
        for k in self.state:
            if k == param:
                output = self.state[k]
                break
        return output
    
    def set_param(self, param, value):
        for k in self.state:
            if k == param:
                self.state[k] = value
                break

    def save(self):
        with open(self.path, 'w') as file:
            json.dump(self.state, file)


def main():
    sys.stdout = TeeOutput(sys.__stdout__)
    sys.stderr = TeeOutput(sys.__stderr__)
    manager = multiprocessing.Manager()
    commands = manager.list()
    replies = manager.list()
    signal = {'kill': False, 'restart_server': False, 'restart_websocket': False, 'termination': False,
              'data': {'commands': commands, 'replies': replies}, 'state': State()}
    
    while not signal['termination']:
        signal['kill'] = False
        threads = []
        threads.append(threading.Thread(target=background, args=(signal, )))
        threads.append(threading.Thread(target=firebase_task, args=(signal, )))
        threads.append(threading.Thread(target=launch_actuator, args=(signal, )))
        threads.append(threading.Thread(target=server_control, args=(signal, )))
        threads.append(threading.Thread(target=websocket_control, args=(signal, )))
        for t in threads:
            t.start()

        while not signal['kill']:
            now = datetime.now()
            if now.hour == RESET_HOUR and now.minute == 0 and now.second == 0:
                signal['kill'] = True
            time.sleep(0.5)

        for t in threads:
            t.join()
        print('RESTART')
        time.sleep(5)

if __name__ == '__main__':
    print('_')
    print('*************************')
    print('      NEW SESSION')
    print('*************************')
    main()