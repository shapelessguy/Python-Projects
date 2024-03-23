import sys
import threading
import time
import requests

from cluster_management.resources_management import Colors, print_col
from prompts import Prompts

compute_uri = f'http://localhost:5000/compute'
stream_uri = f'http://localhost:5000/stream'
prompt = Prompts.Instruct_Alpaca


def get_stream():
    while 1:
        response = requests.post(stream_uri, json={})
        if response.status_code == 200:
            partials = response.json()['partials']
            for l in partials:
                response = l["content"]
                if response == 'END_COMMAND':
                    print('\n', flush=True)
                    return
                print_col(f'{response}', Colors.GREEN, end='')
        else:
            print('Error while sending the request.')
        time.sleep(0.1)


def run():
    settings = {
            'max_new_tokens': 2048,
            'history': {'internal': [], 'visible': []},
            'mode': 'chat',  # Valid options: 'chat', 'chat-instruct', 'instruct'

            'regenerate': False,
            '_continue': False,
            'stop_at_newline': False,
            'chat_prompt_size': 2048,
            'chat_generation_attempts': 1,
            'chat-instruct_command': '',

            # Generation params. If 'preset' is set to different than 'None', the values
            # in presets/preset-name.yaml are used instead of the individual numbers.
            'preset': 'None',
            'do_sample': True,
            'temperature': 1.,
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
            'add_bos_token': True,
            'truncation_length': 2048,
            'ban_eos_token': False,
            'skip_special_tokens': True,
            'stopping_strings': []
    }

    sys.stdout.write(f' ')
    sys.stdout.flush()
    chat = ''
    if prompt['system'] != '':
        system_prompt = input(f'DEFAULT SYSTEM PROMPT:\n{Colors.YELLOW}{prompt["system"]}SYSTEM (default if empty): ')
        sys.stdout.write(f'{Colors.END}\n')
        sys.stdout.flush()
        chat = f"""{prompt['system']}""" if system_prompt == '' else system_prompt

    while 1:
        sys.stdout.write(f'{Colors.RED}')
        user_prompt = input('USER: ')
        sys.stdout.write(f'{Colors.END}')
        chat += f"""{prompt['user']}{user_prompt}\n{prompt['assistant']}"""
        chunk = {
            'settings': settings,
            'allow_devices': None,
            'requests': [
                {
                    'type': 'chat',
                    'async': True,
                    'id': 0,
                    'allow_devices': [5002],
                    'content': chat,
                },
            ]
        }

        threading.Thread(target=get_stream).start()

        print()
        print(chat)
        print(flush=True)

        print_col(f'ASSISTANT: ', Colors.GREEN, end='')
        response = requests.post(compute_uri, json=chunk)

        if response.status_code == 200:
            result = response.json()['result']
            response = result[0]["response"]
            overflow = f'OVERFLOW! ({result[0]["tot_tokens"]} tokens)\n' if result[0]['tot_tokens'] > 2000 else ''
            print_col(overflow, Colors.YELLOW, end='')
        else:
            print('Error while sending the request.')


if __name__ == '__main__':
    run()
