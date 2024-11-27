from server import server_control
from actuators import launch_actuator
from firebase_utils import firebase_task
import multiprocessing
import threading
import sys
from utils import TeeOutput


def background(signal):
    pass


def main():
    sys.stdout = TeeOutput(sys.__stdout__)
    sys.stderr = TeeOutput(sys.__stderr__)
    manager = multiprocessing.Manager()
    threads = []
    commands = manager.list()
    replies = manager.list()
    signal = {'kill': False, 'restart_server': False, 'data': {'commands': commands, 'replies': replies}}
    threads.append(threading.Thread(target=background, args=(signal, )))
    threads.append(threading.Thread(target=firebase_task, args=(signal, )))
    threads.append(threading.Thread(target=launch_actuator, args=(signal, )))
    for t in threads:
        t.start()
    server_control(signal)

    for t in threads:
        t.join()
    print('TERMINATION')

if __name__ == '__main__':
    print('_')
    print('*************************')
    print('      NEW SESSION')
    print('*************************')
    main()