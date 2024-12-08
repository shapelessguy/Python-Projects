from web_tunnel.interface import start_interface, send, wait
import threading
import multiprocessing



def reply(msg, id_):
    print('Received:', msg)


def aknowledge(msg):
    print('ACK', msg)


def background_task(signal):
    try:
        wait(until='ready')
        for _ in range(10):
            send({'a': 'ciao'})
            wait(1)
    except Exception:
        import traceback
        print(traceback.format_exc())


def main(background_task_: callable):
    manager = multiprocessing.Manager()
    signal = manager.dict()
    signal['kill'] = False
    signal['inputs'] = manager.list()
    signal['outputs'] = manager.list()
    signal['ready'] = False
    signal['restart_websocket'] = False
    signal['role'] = 'CLIENT'
    signal['server_ip'] = None
    signal['server_port'] = 9999
    
    threading.Thread(target=background_task_, args=(signal,)).start()
    start_interface(signal, reply, aknowledge)


if __name__ == "__main__":
    main(background_task)
