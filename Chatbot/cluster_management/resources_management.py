import sys
import threading
import time
import traceback
import datetime
import requests
import asyncio
import json
import websockets


if sys.platform == "win32" and (3, 8, 0) <= sys.version_info < (3, 9, 0):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class Colors:
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_dir(msg, color=None, end='\n'):
    sys.stdout.write('\033[2K\033[1G')
    print_col(msg, color, end)
    sys.stdout.write("directive: ")
    sys.stdout.flush()


def print_col(msg, color=None, end='\n'):
    if color is not None:
        sys.stdout.write(color + msg + Colors.END + end)
    else:
        sys.stdout.write(msg + end)
    sys.stdout.flush()


diagnostic_settings = {
    'max_new_tokens': 10,
    'history': {'internal': [], 'visible': []},
    'mode': 'instruct',  # Valid options: 'chat', 'chat-instruct', 'instruct'
    'character': 'Example',
    'instruction_template': 'Vicuna-v1.1',
    'your_name': 'You',

    'regenerate': False,
    '_continue': False,
    'stop_at_newline': False,
    'chat_prompt_size': 2048,
    'chat_generation_attempts': 1,
    'chat-instruct_command': 'Continue the chat dialogue below. Write a single reply for the character "'
                             '<|character|>".\n\n<|prompt|>',
    'preset': 'None',
    'do_sample': True,
    'temperature': 0.7,
    'top_p': 0.1,
    'typical_p': 1,
    'epsilon_cutoff': 0,  # In units of 1e-4
    'eta_cutoff': 0,  # In units of 1e-4
    'tfs': 1,
    'top_a': 0,
    'repetition_penalty': 1.18,
    'top_k': 40,
    'min_length': 0,
    'no_repeat_ngram_size': 0,
    'num_beams': 1,
    'penalty_alpha': 0,
    'length_penalty': 1,
    'early_stopping': False,
    'mirostat_mode': 0,
    'mirostat_tau': 5,
    'mirostat_eta': 0.1,

    'seed': -1,
    'add_bos_token': True,
    'truncation_length': 2048,
    'ban_eos_token': False,
    'skip_special_tokens': True,
    'stopping_strings': []
}


def write_response(command):
    prompt = command.prompt.replace('\n', '\\n') if type(command.prompt) == str else str(command.prompt)
    response = command.response.replace('\n', '\\n') if type(command.response) == str else str(command.response)
    data = {
        'n': command.n,
        'date': datetime.datetime.now(tz=datetime.timezone.utc),
        'prompt_type': command.prompt_type,
        'prompt': prompt,
        'tokens_prompt': command.tokens_prompt,
        'response': response,
        'tokens_response': command.tokens_response
    }
    command.data_ch["db"].data.insert_one(data)


class Command:
    def __init__(self, n, prompt_type, async_, prompt, settings, data_ch, allow_devices=None):
        self.n = n
        self.prompt_type = prompt_type
        self.async_ = async_
        self.prompt = prompt
        self.n_words = len(prompt.split() if type(prompt) == str else prompt)
        self.settings = settings
        self.flag_resp = False
        self.allow_devices = allow_devices
        self.response = ""
        self.tokens_prompt = -1
        self.tokens_response = -1
        self.data_ch = data_ch

    def reply_to_dict(self):
        reply = {
            'type': self.prompt_type,
            'id': self.n,
            'date': str(datetime.datetime.now(tz=datetime.timezone.utc)),
            'content': self.prompt,
            'response': self.response,
            'tot_tokens': self.tokens_prompt + self.tokens_response
        }
        return reply

    def def_request(self):
        return {
            'user_input': self.prompt,
            **self.settings
        }

    def def_prompt(self):
        return {'prompt': self.prompt,
                'add_special_tokens': False,
                'add_bos_token': False}

    def def_embeddings(self):
        return {'input_texts': self.prompt}

    def set_response(self, response, resp_block, resource):
        self.flag_resp = True
        self.response = response[resp_block][0] if resp_block == 'embeddings' else response[resp_block]
        if 'tokens_response' in response:
            self.tokens_response = response['tokens_response']
        self.tokens_prompt = response['tokens_prompt'] if 'tokens_prompt' in response else self.tokens_response

        write_response(self)
        tokens = f' ({self.tokens_response} tokens)' if self.tokens_response > -1 else ''
        print_dir(f'{resource.port} -> Response to command {self.n}{tokens} given.', Colors.GREEN)


class Resource:
    def __init__(self, type_, address, available):
        self.type = type_
        self.address = address
        host = address.split(":")[0]
        port_str = address.split(":")[1]
        port = int(port_str) if port_str != 'None' else 0
        self.port = port
        self.chat_api = f'http://{host}:{port + 1000}/api/v1/chat'
        self.tokenize_api = f'http://{host}:{port + 1000}/api/v1/tokenize'
        self.stringify_api = f'http://{host}:{port + 1000}/api/v1/stringify'
        self.encode_api = f'http://{host}:{port + 1000}/api/v1/encode'
        self.stream_api = f'ws://{host}:{port + 2000}/api/v1/stream'
        self.available = available
        self.status = "free"

    def __str__(self):
        return f'{self.type}, {self.address}, {self.available}, {self.status}'


class ResourcePool(list):
    def __init__(self):
        super().__init__()
        self.available_resources = []

    def insert_resource(self, type_, address, available):
        for element in self:
            if address == element.address:
                element.available = available
                return
        self.append(Resource(type_, address, available))

    def update_avail_resources(self):
        self.available_resources = []
        for element in self:
            if element.available:
                self.available_resources.append(element)

    def get_avail_resources(self, allow_devices=None):
        if allow_devices is not None:
            return [x for x in self.available_resources if x.port in allow_devices]
        else:
            return self.available_resources


# noinspection PyBroadException
def pull(command, request, api, json_req, res_block, resource):
    try:
        response = requests.post(api, json=json_req)
        if response.status_code == 200:
            result = response.json()['results'][0]
            command.set_response(result, res_block, resource)
            request[1] = 'computed'
        else:
            print_dir(f'{resource.port} -> Status code: {response.status_code}')
            request[1] = 'to_be_computed'
    except Exception:
        print_dir(traceback.format_exc())
        request[1] = 'to_be_computed'


# noinspection PyBroadException
async def pull_async(command, request, api, json_req, res_block, resource):
    try:
        ov_response, tokens_response = "", 0
        async for response in req_pull_async(command, request, api, json_req, res_block, resource):
            tokens_response += 1
            command.data_ch['stream_buffer'] += [{'id': command.n, 'content': response}]
            command.data_ch['stream_flag'] = True
            ov_response += response
        result = {res_block: [ov_response], 'tokens_response': tokens_response, 'tokens_prompt': 0}
        command.set_response(result, res_block, resource)
        request[1] = 'computed'
    except Exception:
        print_dir(f'{resource.port} -> Stream error.')
        request[1] = 'to_be_computed'
    command.data_ch['stream_buffer'] += [{'id': command.n, 'content': 'END_COMMAND'}]
    command.data_ch['stream_flag'] = True


async def req_pull_async(command, request, api, json_req, res_block, resource):
    async with websockets.connect(api, ping_interval=None) as websocket:
        json_req['prompt'] = json_req['user_input']
        await websocket.send(json.dumps(json_req))

        while True:
            incoming_data = await websocket.recv()
            incoming_data = json.loads(incoming_data)
            if incoming_data['event'] == 'text_stream':
                yield incoming_data['text']
            elif incoming_data['event'] == 'stream_end':
                return


def req(request, resource):
    command = request[0]

    if command.prompt_type == 'chat' or command.prompt_type == 'simple_request':
        api = resource.chat_api
        json_req = command.def_request()
        res_block = 'history'
        if command.async_:
            asyncio.run(pull_async(command, request, resource.stream_api, json_req, res_block, resource))
        else:
            pull(command, request, resource.chat_api, json_req, res_block, resource)
    elif command.prompt_type == 'encode':
        api = resource.encode_api
        json_req = command.def_embeddings()
        res_block = 'embeddings'
        pull(command, request, api, json_req, res_block, resource)
    elif command.prompt_type == 'stringify':
        api = resource.stringify_api
        json_req = command.def_prompt()
        res_block = 'text'
        pull(command, request, api, json_req, res_block, resource)
    elif command.prompt_type == 'tokenize':
        api = resource.tokenize_api
        json_req = command.def_prompt()
        res_block = 'encoded'
        pull(command, request, api, json_req, res_block, resource)
    else:
        print_dir(f'Bad request format: {command.prompt_type}??')
        raise


def compute_queue(data_ch):
    while data_ch['resource_pool'] is None:
        time.sleep(0.1)
    print_dir('NODES READY', Colors.YELLOW)
    while 1:
        if len(data_ch['chunks']) > 0:
            chunk = data_ch['chunks'].pop(0)
            settings = chunk['settings']
            allow_devices = chunk['allow_devices']
            inputs = [Command(inp['id'], inp['type'], inp['async'],
                              (inp['content'] if inp['type'] != 'single_request'
                               else f"""USER: {inp['content']}\n ASSISTANT: """),
                              settings, data_ch, inp['allow_devices']) for inp in chunk['requests']]

            resource_pool = data_ch['resource_pool']
            diagnostic_request = [Command(-1, 'simple_request', False, 'example_text',
                                          diagnostic_settings, data_ch), 'to_be_computed']
            all_requests = [[inp, 'to_be_computed'] for inp in inputs]
            free_resources = [x for x in resource_pool.get_avail_resources(allow_devices=allow_devices)]
            if len(free_resources) == 0:
                raise "NO RESOURCES AVAILABLE"
            busy_resources = []
            err_resources = []
            tasks = []

            while sum([1 if x[1] == 'to_be_computed' else 0 for x in all_requests]) > 0:
                for resource in free_resources:
                    ar = [x for x in all_requests if x[0].allow_devices is None or resource.port in x[0].allow_devices]
                    for request in ar:
                        if request[1] == 'to_be_computed':
                            request[1] = 'computing'
                            tasks.append([threading.Thread(target=req, args=(request, resource)), resource, request])
                            tasks[-1][0].start()
                            resource.status = 'busy'
                            busy_resources.append(free_resources.pop(free_resources.index(resource)))
                            break
                for i in range(len(tasks))[::-1]:
                    if not tasks[i][0].is_alive():
                        resource = tasks[i][1]
                        if tasks[i][-1][1] != 'computed':
                            diagnostics = threading.Thread(target=req, args=(diagnostic_request, resource))
                            diagnostics.start()
                            diagnostics.join()
                            if diagnostic_request[1] != 'computed':
                                resource.status = 'error'
                                err_resources.append(busy_resources.pop(busy_resources.index(resource)))
                                print_dir(f"RESOURCE {resource.chat_api} NOT RESPONDING")
                            else:
                                resource.status = 'free'
                                free_resources.append(busy_resources.pop(busy_resources.index(resource)))
                        else:
                            resource.status = 'free'
                            free_resources.append(busy_resources.pop(busy_resources.index(resource)))
                        tasks.pop(i)
                if sum(1 if x[1] != 'computed' else 0 for x in all_requests) == 0:
                    return
                time.sleep(0.05)
            while sum([1 if x[1] == 'computing' else 0 for x in all_requests]) > 0:
                time.sleep(0.1)
            print_dir('Computation on chunk completed.')
            data_ch['results'] += [inputs]
            data_ch['send_back'] = True
            data_ch['resources_update'] = True
        else:
            data_ch['resources_update'] = True
            time.sleep(0.5)
