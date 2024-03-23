import requests

from cluster_management.resources_management import Colors, print_dir

URI = f'http://localhost:5000/compute'


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

    chunk = {
        'settings': settings,
        'allow_devices': None,
        'requests': [
            # {
            #     'type': 'chat',
            #     'async': False,
            #     'id': 0,
            #     'allow_devices': [5005, 5006, 5007, 5008],
            #     'content': f"""USER: Who am I?\nASSISTANT: """,
            # },
            {
                'type': 'simple_request',
                'async': False,
                'id': 1,
                'allow_devices': [5005, 5006, 5007, 5008],
                'content': f"""Tell me a story in about 50 sentences."""
            },
            # {
            #     'type': 'tokenize',
            #     'async': False,
            #     'id': 2,
            #     'allow_devices': [5005, 5006, 5007, 5008],
            #     'content': f"""USER: Summarize me the following text in one line: 'you are ugly'\nASSISTANT: """
            # },
            # {
            #     'type': 'encode',
            #     'async': False,
            #     'id': 3,
            #     'allow_devices': [5005, 5006, 5007, 5008],
            #     'content': f"""USER: Summarize me the following text in one line: 'you are ugly'\nASSISTANT: """
            # },
        ]
    }

    response = requests.post(URI, json=chunk)
    if response.status_code == 200:
        result = response.json()['result']
        for l in result:
            print_dir('---------------------------------------------------------------------------')
            overflow = f' - OVERFLOW! ({l["tot_tokens"]} tokens)' if l['tot_tokens'] > 2000 else ''
            print_dir(f'Type: {l["type"]}{overflow}', Colors.YELLOW)
            print_dir(f'Prompt: {l["content"]}', Colors.RED)
            response = l["response"] if l['type'] != 'encode' else '-- Encoded vector --'
            print_dir(f'Response: {response}', Colors.GREEN)
            print_dir('')
    else:
        print('Error while sending the request.')


if __name__ == '__main__':
    run()
