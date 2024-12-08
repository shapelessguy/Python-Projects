from web_tunnel.webclient import websocket_control
from web_tunnel.firebase_utils import firebase_task
import threading
import time
import uuid
signal = None


def wait(seconds=None, until=None):
    if until is not None:
        if until == 'ready':
            while signal is None:
                time.sleep(0.1)
            while not signal['kill']:
                if signal['ready']:
                    break
                time.sleep(0.1)
        else:
            raise Exception(f'Unknown until="{until}" condition.')
        print(signal['ready'])
        return
    if seconds < 0.5:
        time.sleep(seconds)
    else:
        counter = 0
        while counter < seconds:
            if signal is not None and signal['kill']:
                break
            time.sleep(0.1)
            counter += 0.1
    if signal['kill']:
        raise Exception("Time to kill.")


def send(msg, id_=None):
    request_id = str(uuid.uuid4()) if id_ is None else id_
    signal['inputs'].append({'__id__': request_id, 'data': msg})
    return request_id


def reply_cb(reply_funct, aknowledge_funct):
    while not signal['kill']:
        if len(signal['outputs']) > 0:
            output = signal['outputs'].pop(0)
            if 'data' in output and '__id__' in output:
                reply_funct(output['data'], output['__id__'])
            else:
                aknowledge_funct(output)
        time.sleep(0.05)


def start_interface(signal_, reply_funct: callable, aknowledge_funct: callable):
    global signal
    signal = signal_
    threads = []
    threads.append(threading.Thread(target=firebase_task, args=(signal, 'read')))
    threads.append(threading.Thread(target=websocket_control, args=(signal,)))
    threads.append(threading.Thread(target=reply_cb, args=(reply_funct, aknowledge_funct)))
    for t in threads:
        t.start()

    prev_ip = signal['server_ip']
    while not signal['kill']:
        if prev_ip != signal['server_ip']:
            signal['restart_websocket'] = True
            prev_ip = signal['server_ip']
        time.sleep(0.5)

    for t in threads:
        t.join()