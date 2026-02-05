from server import server_control
from websocket_server import websocket_control
from actuators import launch_actuator
from trackIp_utils import trackIp_task
from announcements import *
from utils import TeeOutput, HOSTNAME
from datetime import datetime
import subprocess
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


def force_kill_by_port_linux(port):
    command = f"sudo kill -9 $(sudo lsof -t -i :{port})"
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Successfully killed process using port {port}")
    except subprocess.CalledProcessError:
        print(f"Failed to kill process on port {port} — maybe no process is using it or permission denied.")


def main():
    manager = multiprocessing.Manager()
    commands = manager.list()
    replies = manager.list()
    signal = {'kill': False, 'restart_server': False, 'restart_websocket': False, 'termination': False,
              'data': {'commands': commands, 'replies': replies}, 'state': State(), 'log_file_name': None}
    while not signal['termination']:
        signal['log_file_name'] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.log")
        sys.stdout = TeeOutput('MAIN', sys.__stdout__, signal['log_file_name'])
        sys.stderr = TeeOutput('MAIN', sys.__stderr__, signal['log_file_name'])
        signal['kill'] = False
        threads = []
        # threads.append(threading.Thread(target=background, args=(signal, )))
        threads.append(threading.Thread(target=trackIp_task, args=(signal, )))
        threads.append(threading.Thread(target=spawn_monitoring, args=(signal, )))
        threads.append(threading.Thread(target=launch_actuator, args=(signal, )))
        threads.append(threading.Thread(target=server_control, args=(signal, )))
        # threads.append(threading.Thread(target=websocket_control, args=(signal, )))
        for t in threads:
            t.start()

        while not signal['kill']:
            now = datetime.now()
            if now.hour == RESET_HOUR and now.minute == 0:
                try:
                    subprocess.run(["sudo", "reboot"], check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Reboot command failed: {e}")
                except PermissionError:
                    print("Permission denied — probably not running as root")
            time.sleep(0.5)

        for t in threads:
            t.join()
        print('RESTART')
        force_kill_by_port_linux(HOSTNAME['websocket_port'])
        force_kill_by_port_linux(HOSTNAME['server_port'])
        time.sleep(10)

if __name__ == '__main__':
    print('_')
    print('*************************')
    print('      NEW SESSION')
    print('*************************')
    main()
