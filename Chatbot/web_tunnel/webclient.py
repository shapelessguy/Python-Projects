import multiprocessing
import socketio
import time


def start_websocket_client(signal):
    sio = socketio.Client()

    @sio.event
    def connect():
        print("Connected to WebSocket server")
        sio.emit('whoami', signal['role'])

    @sio.on('message')
    def handle_message(data):
        if 'all_connected' in data:
            signal['ready'] = data['all_connected']
        signal['outputs'].append(data)

    @sio.event
    def disconnect():
        signal['ready'] = False
        print("Disconnected from WebSocket server")
    
    sio.connect(f'http://{signal["server_ip"]}:{signal["server_port"]}')

    while not signal['kill'] and not signal['restart_websocket']:
        if len(signal['inputs']) > 0:
            input_ = signal['inputs'].pop(0)
            sio.emit('message', input_)
        time.sleep(0.05)


def websocket_control(signal):
    init = True
    p = None
    while not signal['kill']:
        signal['restart_websocket'] = False
        try:
            if not init:
                p = multiprocessing.Process(target=start_websocket_client, args=(signal, )) 
                p.start()
            init = False
            while not signal['kill'] and not signal['restart_websocket']:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        except Exception:
            pass

    signal['kill'] = True
    if p is not None:
        p.kill()
        print('Websocket killed')
    print('Websocket control terminated.')


if __name__ == "__main__":
    pass
