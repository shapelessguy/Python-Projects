import time
import sys
import multiprocessing
import multiprocessing
import logging
import uuid
from flask import Flask, request, jsonify
from utils import TeeOutput, HOSTNAME
from actuators import endpoints as actuators_endpoints


def random_id():
    return uuid.uuid4().hex[:12]


def start_flask_server(signal):
    sys.stdout = TeeOutput('FLASK', sys.__stdout__, signal['log_file_name'])
    sys.stderr = TeeOutput('FLASK', sys.__stderr__, signal['log_file_name'])
    app = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    endpoints = actuators_endpoints

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

                    req_id = random_id()
                    reply = None
                    signal['data']['commands'].append({"endpoint": ep, "req_id": req_id, **data})
                    while not signal["kill"]:
                        found = False
                        for i in range(len(signal["data"]["replies"])):
                            if signal["data"]["replies"][i]["req_id"] == req_id:
                                reply = signal["data"]["replies"].pop(i)
                                found = True
                                break
                        if found:
                            break
                        time.sleep(0.1)
                    status, code = ('success', 200) if "error" not in reply else ('error', 500)
                    return jsonify({'status': status, 'command': {"endpoint": ep, **data}, 'reply': reply}), code
                except Exception:
                    import traceback
                    print(f"Error processing request: \n{traceback.format_exc()}")
                    return jsonify({'error': "Internal server error"}), 500
        
        create_route(endpoint)

    print(f"Server bound to port {HOSTNAME['server_port']}")
    app.run(host='0.0.0.0', port=HOSTNAME['server_port'])


def server_control(signal):
    init = False
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
