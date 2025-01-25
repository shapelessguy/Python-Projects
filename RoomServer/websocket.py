import time
import sys
import multiprocessing
from flask import Flask, request, jsonify, render_template
import multiprocessing
import logging
from flask_socketio import SocketIO, send, emit
from utils import TeeOutput, HOSTNAME


def start_websocket(signal):
    sys.stdout = TeeOutput('WEBSOCKET', sys.__stdout__, signal['log_file_name'])
    sys.stderr = TeeOutput('WEBSOCKET', sys.__stderr__, signal['log_file_name'])
    app = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    connected_clients = {}
    socketio = SocketIO(app)
    socketio.all_connected = False

    @app.route('/')
    def index():
        return {'/': '200'}

    @socketio.on('connect')
    def on_connect():
        client_id = request.sid

    @socketio.on('whoami')
    def on_whoami(role):
        client_id = request.sid
        connected_clients[client_id] = (request.namespace, role)
        print(f"Client connected: {client_id} - {role}")
        client, server = False, False
        for c in connected_clients:
            if connected_clients[c][1] == 'CLIENT':
                client = True
            elif connected_clients[c][1] == 'SERVER':
                server = True
        socketio.all_connected = client and server
        send_to('ALL', {"client_id": request.sid, "role": role, "all_connected": socketio.all_connected})

    @socketio.on('disconnect')
    def on_disconnect():
        client_id = request.sid
        print(f"Client disconnected: {client_id}")
        connected_clients.pop(client_id, None)

    @socketio.on('message')
    def handle_message(msg):
        if isinstance(msg, dict):
            print(f"Received JSON message from {request.sid}: {msg}")
            role = connected_clients[request.sid][1]
            if socketio.all_connected:
                send_to('CLIENT' if role == 'SERVER' else 'SERVER', msg)
                emit('message', {"__id__": msg['__id__'], "status": "200", "error": ""}, room=request.sid)
            else:
                emit('message', {"__id__": msg['__id__'], "status": "error", "error": "Not all connected"}, room=request.sid)
        else:
            print(f"Received non-JSON message from {request.sid}: {msg}")
            emit('message', {"__id__": msg['__id__'], "status": "error", "error": "Invalid message format"}, room=request.sid)

    def send_to(dest, message):
        for client_id in connected_clients.copy():
            if dest == 'ALL' or connected_clients[client_id][1] == dest:
                emit('message', message, room=client_id)
                print(f"Message sent to {dest} {client_id}: {message}")
    
    socketio.run(app, host='0.0.0.0', port=HOSTNAME['websocket_port'])


def websocket_control(signal):
    init = True
    p = None
    while not signal['kill']:
        signal['restart_websocket'] = False
        try:
            if not init:
                p = multiprocessing.Process(target=start_websocket, args=(signal, )) 
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


if __name__ == '__main__':
    signal = {'kill': False, 'restart_websocket': False}
    websocket_control(signal)
