import json
import sys
import threading
import time
import numpy as np
import pymongo
import requests
from start_clusters import resources
from resources_management import ResourcePool, compute_queue, print_dir, Colors
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

cur_status = [["Updating.."]]
func_status = []
glob_data_ch = {}


def get_status(node_pool, data_ch):
    str_matrix = []
    for node in node_pool:
        str_matrix.append([f"{node.__class__.__name__} {node.server_on}"])
        for i in range(4):
            port = node.ports[i] if len(node.ports) > i else 'None'
            if data_ch['stop']:
                return None
            http_address = f"{node.server_on}:{port}"
            uri = f'http://{http_address}/api/v1/ping'
            status = ""
            # noinspection PyBroadException
            try:
                response = requests.post(uri, json={}, timeout=0.7)
                status = "ON"
            except:
                status = "OFF"
            str_matrix[-1].append(f"{port}, {status}")
    max_col = max([len(l) for l in str_matrix])
    for l_ in str_matrix:
        l_ = l_ + [""] * (max_col - len(l_))
    str_matrix = np.array(str_matrix).T
    return str_matrix


def print_status(status):
    text = ""
    for line in status:
        for v in line:
            text += '%30s' % v
        text += '\n'
    return text


def append_log(log):
    with open('watchdog_log.txt', 'a+') as file:
        file.write(f'{int(time.time())} {log}\n')


def write_status(node_status):
    with open('cluster_status.json', 'w') as file:
        json.dump(node_status, file)


def watch_status(node_pool, data_ch):
    def get_node_props(status):
        nodes_ = {}
        for n in status.T:
            for v in n[1:]:
                props = tuple([n[0]] + v.split(', '))
                key = props[0] + " " + props[1]
                nodes_[key] = props[2]
        return nodes_
    append_log("watchdog start")
    global cur_status, func_status
    cur_status = get_status(node_pool, data_ch)

    func_status = {}
    if data_ch['resources_update']:
        resource_pool = ResourcePool()
        for i in range(1, len(cur_status)):
            for j in range(len(cur_status[i])):
                resource_pool.insert_resource(cur_status[0][j].split()[0], cur_status[0][j].split()[1] + ":" +
                                              cur_status[i][j].split(', ')[0], cur_status[i][j].split(', ')[1] == 'ON')
        resource_pool.update_avail_resources()
        data_ch['resources_update'] = False
        data_ch['resource_pool'] = resource_pool

    if cur_status is None:
        return
    cur_nodes = get_node_props(cur_status)
    for k in cur_nodes:
        append_log(f'{k} {cur_nodes[k]}')
    write_status(cur_nodes)
    append_log("watchdog regime")
    while not data_ch['stop']:
        for i in range(5):
            time.sleep(0.5)
            if data_ch['stop']:
                return
        n_status = get_status(node_pool, data_ch)
        if n_status is None:
            return
        if not np.array_equal(n_status, cur_status):
            n_nodes = get_node_props(n_status)
            for k in cur_nodes:
                if cur_nodes[k] != n_nodes[k]:
                    append_log(f'{k} {n_nodes[k]}')
            cur_status = n_status
            cur_nodes = n_nodes
            write_status(n_nodes)
            print_dir('\nSTATUS UPDATE:\n' + print_status(cur_status), Colors.BLUE)


def monitor():
    global glob_data_ch
    node_pool = resources()
    client = pymongo.MongoClient(f"mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
    
    data_ch = {'stop': False,
               'resources_update': True,
               'resource_pool': None,
               'chunks': [],
               'results': [],
               'send_back': False,
               'stream_buffer': [],
               'stream_flag': False,
               'db': client["LLM"]
               }
    
    glob_data_ch = data_ch
    watchdog = threading.Thread(target=watch_status, args=(node_pool, data_ch))
    watchdog.start()
    computation = threading.Thread(target=compute_queue, args=(data_ch, ))
    computation.start()
    chunk_server = threading.Thread(target=_run_server, args=(data_ch, ))
    chunk_server.start()
    db = glob_data_ch['db']

    while 1:
        directive = input('')
        directive = directive.split()
        if directive[0] == 'status':
            print(print_status(cur_status))
            sys.stdout.write("directive: ")
        elif directive[0] == 'db':
            # print(db.)
            sys.stdout.write("directive: ")
        elif directive[0] == 'exit':
            append_log("watchdog end")
            break
        else:
            sys.stdout.write("Unknown directive\ndirective: ")
    data_ch['stop'] = True
    print_dir('Terminate')


# noinspection PyPep8Naming
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.end_headers()
            response = json.dumps({
                'result': 0
            })

            self.wfile.write(response.encode('utf-8'))
        else:
            self.send_error(404)

    # noinspection PyShadowingBuiltins
    def log_message(self, format, *args):
        return

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = json.loads(self.rfile.read(content_length).decode('utf-8'))
        global glob_data_ch

        if self.path == '/compute':
            print_dir('Request received.', Colors.RED)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            glob_data_ch['chunks'] += [body]

            while not glob_data_ch['send_back']:
                time.sleep(0.1)

            replies = []
            for result in glob_data_ch['results']:
                for inp in result:
                    replies += [inp.reply_to_dict()]

            glob_data_ch['send_back'] = False
            glob_data_ch['results'] = []

            response = json.dumps({
                'result': replies
            })

            self.wfile.write(response.encode('utf-8'))

        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            partials = []
            for item in glob_data_ch['stream_buffer']:
                partials += [item]
            response = json.dumps({
                'partials': partials
            })
            glob_data_ch['stream_buffer'] = []

            self.wfile.write(response.encode('utf-8'))

        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()


def _run_server(data_ch):
    address = '0.0.0.0'
    port = 5000
    server = ThreadingHTTPServer((address, port), Handler)
    print(f'Starting API at http://{address}:{port}/api')
    server.serve_forever()


if __name__ == "__main__":
    monitor()
