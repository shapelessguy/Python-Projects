import time
import sys
import multiprocessing
from flask import Flask, request, jsonify
import multiprocessing
import logging
from utils import TeeOutput, HOSTNAME


def start_flask_server(signal):
    sys.stdout = TeeOutput('FLASK', sys.__stdout__, signal['log_file_name'])
    sys.stderr = TeeOutput('FLASK', sys.__stderr__, signal['log_file_name'])
    app = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    endpoints = ['lights', 'strip', 'tv', 'audio', 'announce']

    @app.route("/")
    def ping_callback():
        print('PING')
        return {'/': '200'}

    for endpoint in endpoints:
        def create_route(ep):
            @app.route(f"/{ep}", endpoint=f"callback_{ep}", methods=["POST"])
            def cb():
                try:
                    data = request.get_json()
                    if not data:
                        print("No JSON data in request.")
                        return jsonify({'error': "Request must include JSON data"}), 400

                    if ep not in data:
                        print(f"Missing '{ep}' field in request.")
                        return jsonify({'error': f"Missing '{ep}' field"}), 400

                    if 'audio' not in data or data['audio'] != "pingvol":
                        print(f"{ep.upper()}: {data}")
                    command = ep.upper() + data[ep].upper()
                    signal['data']['commands'].append(command)

                    return jsonify({'status': 'success', 'command': command}), 200
                except Exception as e:
                    print(f"Error processing request: {e}")
                    return jsonify({'error': "Internal server error"}), 500
        
        create_route(endpoint)

    app.run(host='0.0.0.0', port=HOSTNAME['server_port'])


def server_control(signal):
    init = True
    p = None
    while not signal['kill']:
        signal['restart_server'] = False
        try:
            if not init:
                p = multiprocessing.Process(target=start_flask_server, args=(signal, )) 
                p.start()
            init = False
            while not signal['kill'] and not signal['restart_server']:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        except Exception:
            pass

    signal['kill'] = True
    if p is not None:
        p.kill()
        print('Flask server killed')
    print('Server control terminated.')


if __name__ == '__main__':
    signal = {'kill': False, 'restart_server': False}
    server_control(signal)
