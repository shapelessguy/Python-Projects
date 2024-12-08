from web_tunnel.interface import start_interface, send, wait
import threading
import multiprocessing
import time


def reply(msg, id_):
    print('Received:', msg)
    for i in range(10):
        time.sleep(0.1)
        send(f'Hello bro! {i}', id_)


def aknowledge(msg):
    print('ACK', msg)


def background_task(signal):
    try:
        wait(0)
        pass
    except Exception:
        pass


def main(background_task_: callable):
    manager = multiprocessing.Manager()
    signal = manager.dict()
    signal['kill'] = False
    signal['inputs'] = manager.list()
    signal['outputs'] = manager.list()
    signal['ready'] = False
    signal['restart_websocket'] = False
    signal['role'] = 'SERVER'
    signal['server_ip'] = None
    signal['server_port'] = 9999
    
    threading.Thread(target=background_task_, args=(signal,)).start()
    start_interface(signal, reply, aknowledge)


if __name__ == "__main__":
    main(background_task)
