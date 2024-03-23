import os
import json
import tiktoken
from dotenv import dotenv_values
import openai
from chat_manager import get_all_chats, new_chat
import colorama
colorama.init()

YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
GREEN = '\033[92m'
BOLD = '\033[1m'
GRAY = '\033[90m'
UNDERLINE = '\033[4m'
END = '\033[0m'

colors = {
    'system': YELLOW,
    'user': RED,
    'assistant': GREEN,
    'title': CYAN,
    'tokens_count': GRAY,
}

def_sys_pmt = "You are a good assistant and you will answer all the user's questions at the best of your capabilities"

openai.organization = dotenv_values(".env")['OPENAI_ORG']
openai.api_key = dotenv_values(".env")['OPENAI_KEY']
main_path = dotenv_values(".env")['MAIN_PATH']
chat_dir = os.path.join(main_path, 'chats')

if not os.path.exists(chat_dir):
    os.mkdir(chat_dir)

with open('consumption.json', 'r') as file_:
    consumption = json.load(file_)

def_model = 'gpt-3.5-turbo-0613'
encoding = tiktoken.encoding_for_model(def_model)


def context_creation(chunks):
    context_ = ''
    for chunk in chunks:
        context_ += f'{chunk["role"].title()}: {chunk["content"]}\n\n'
    return context_


def get_consumption():
    with open('consumption.json', 'r') as file:
        d = json.load(file)
        for k, v in d.items():
            print(f'{k.title()}: {v}')


def format_message(msg_, role_show=True):
    if msg_['role'] == 'system':
        color = colors['system']
    elif msg_['role'] == 'user':
        color = colors['user']
    else:
        color = colors['assistant']
    role = f'{msg_["role"].title()}: ' if role_show else ''
    return f'{color}{role}{msg_["content"]}{END}'


def format_message_stream(text):
    msg_ = {'role': 'assistant', 'content': text}
    return format_message(msg_, role_show=False)


def update_title(chat):
    if chat.chat_info['last_update'] != chat.chat_info['last_title_update']:
        request_title(chat, model=def_model, cost=consumption)


def update_titles(chats):
    for chat in chats:
        update_title(chat)


def request_stream(chat_, message_: list, model, cost):
    reply = openai.ChatCompletion.create(
        model=model,
        messages=chat_.chat_info['history'] + message_,
        stream=True
    )

    gen_tokens = 0
    reply_text = ''
    print(format_message_stream('Assistant: '), end='')
    for r in reply:
        gen_tokens += 1
        if 'content' in r['choices'][0]['delta']:
            reply_text += r['choices'][0]['delta']['content']
            print(format_message_stream(r['choices'][0]['delta']['content']), end='', flush=True)
    print()

    chat_.chat_info['history'].append({'role': 'assistant', 'content': reply_text})
    chat_.save()

    context_ = context_creation(chat_.chat_info['history'])
    print(f'{colors["tokens_count"]}Conversation tokens (approx): {len(encoding.encode(context_))}{END}')
    cost['prompt_tokens'] = int(cost.get('prompt_tokens', 0)) + len(encoding.encode(context_))
    cost['completion_tokens'] = int(cost.get('completion_tokens', 0)) + gen_tokens

    cost['cost'] = str(round(cost['prompt_tokens'] * 0.0000015 + cost['completion_tokens'] * 0.000002, 4)) + '$'
    with open('consumption.json', 'w') as f:
        json.dump(consumption, f)


def request_title(chat_, model, cost):
    print(f'Finding a title for chat {chat_.index}')
    reply = openai.ChatCompletion.create(
        model=model,
        messages=chat_.chat_info['history'] + [
                    {
                        'role': 'user',
                        'content': 'Summarize the entire conversation so far in a sentence of at most 20 words.'
                    }],
        max_tokens=100
    )

    rep_msg = reply['choices'][0]['message']
    print(f'Summarization: {rep_msg["content"]}')
    chat_.chat_info['title'] = rep_msg["content"]
    chat_.chat_info['last_title_update'] = chat_.chat_info['last_update']
    chat_.save(update=False)

    cost['prompt_tokens'] = int(cost.get('prompt_tokens', 0)) + reply['usage']['prompt_tokens']
    cost['completion_tokens'] = int(cost.get('completion_tokens', 0)) + reply['usage']['completion_tokens']
    cost['cost'] = str(round(cost['prompt_tokens'] * 0.0000015 + cost['completion_tokens'] * 0.000002, 4)) + '$'
    with open('consumption.json', 'w') as f:
        json.dump(consumption, f)


def request(chat_, message_: list, model, cost):
    reply = openai.ChatCompletion.create(
        model=model,
        messages=chat_.chat_info['history'] + message_,
        max_tokens=100
    )

    rep_msg = reply['choices'][0]['message']
    print(format_message(rep_msg))
    chat_.chat_info['history'].append(rep_msg)
    chat_.save()

    context_ = context_creation(chat_.chat_info['history'])
    print(f'{colors["tokens_count"]}Conversation tokens (approx): {len(encoding.encode(context_))}{END}')
    cost['prompt_tokens'] = int(cost.get('prompt_tokens', 0)) + reply['usage']['prompt_tokens']
    cost['completion_tokens'] = int(cost.get('completion_tokens', 0)) + reply['usage']['completion_tokens']
    cost['cost'] = str(round(cost['prompt_tokens'] * 0.0000015 + cost['completion_tokens'] * 0.000002, 4)) + '$'
    with open('consumption.json', 'w') as f:
        json.dump(consumption, f)


all_commands = {
    'list commands': "Lists all commands available for super-user.",
    'list chats': "Lists all the stored chats.",
    'new': "Creates a new chat. It will be saved on HHD only if at least one reply will be generated",
    'title update': "Updates titles of the not up-to-date chats. This command might be expensive in terms of tokens.",
    'join X': "Joins one of the stored chats. X is the ID of the specified chat.",
    'join last': "Joins the last chat that has been created.",
    'consumption': "Shows the overall consumption of tokens.",
    'exit': "Quits the shell."
}
all_sub_commands = {
    'list commands': "Lists all commands available for this chat.",
    'chat mode': "Joins the actual chat.",
    'title update': "Updates the title of the current chat with an auto-generated summarization of the conversation.",
    'count tokens': "Counts the total number of tokens of the current conversation.",
    'delete': "Deletes the current chat.",
    'consumption': all_commands['consumption'],
    'exit': "Quits the current chat instance."
}


def serve():
    com, chats = ['new', 'chat', 'mode'], []
    while 1:
        if len(com) == 0:
            chats = get_all_chats(chat_dir)
            com = input('Super-user command: ').split()
        if com[0] == 'exit':
            break
        elif com[0] == 'list' and com[1] == 'commands':
            for k, v in all_commands.items():
                print(f'{k:>15}: {v}')
            com = []
        elif com[0] == 'list' and com[1] == 'chats':
            chats = get_all_chats(chat_dir)
            for chat in chats:
                print(chat)
            com = []
        elif com[0] == 'new':
            chats.append(new_chat(chat_dir))
            com = ['join', 'last'] + com[1:]
        elif com[0] == 'title' and com[1] == 'update':
            update_titles(get_all_chats(chat_dir))
            com = []
        elif com[0] == 'consumption':
            get_consumption()
            com = []
        elif com[0] == 'join':
            if com[1] == 'last':
                index = max([x.index for x in chats])
            else:
                index = int(com[1])
            chat = [x for x in chats if x.index == index]
            if len(chat) > 0:
                chat = chat[0]
                print(f'Joined chat {index} - {chat.chat_info["title"]}')
                chat_mode = False if len(com) < 4 else com[2] == 'chat' and com[3] == 'mode'
                sub_com = [] if not chat_mode else ['chat', 'mode']
                while 1:
                    if len(sub_com) == 0:
                        sub_com = input('Chat command: ').split()
                    if sub_com[0] == 'exit':
                        break
                    elif sub_com[0] == 'list' and sub_com[1] == 'commands':
                        for k, v in all_sub_commands.items():
                            print(f'{k:>15}: {v}')
                        sub_com = []
                    elif sub_com[0] == 'set' and sub_com[1] == 'title':
                        chat.chat_info['title'] = input(f'{colors["title"]}TITLE: ')
                        print(f'{END}', end='')
                        chat.chat_info['last_title_update'] = chat.chat_info['last_update']
                        chat.save(update=False)
                        sub_com = []
                    elif sub_com[0] == 'count' and sub_com[1] == 'tokens':
                        context = context_creation(chat.chat_info['history'])
                        print(f'Tokens approximation: {len(encoding.encode(context))}')
                        sub_com = []
                    elif sub_com[0] == 'delete':
                        chat = chats.pop(chats.index(chat))
                        chat.delete()
                        sub_com = ['exit']
                    elif sub_com[0] == 'chat' and sub_com[1] == 'mode':
                        if len(chat.chat_info['history']) != 0:
                            for msg in chat.chat_info['history']:
                                print(format_message(msg))
                        while 1:
                            message = []
                            if len(chat.chat_info['history']) == 0:
                                sys_prompt = input(f'{colors["system"]}System (default if empty): ')
                                print(f'{END}', end='')
                                if sys_prompt == "":
                                    sys_prompt = def_sys_pmt
                                if sys_prompt == 'exit':
                                    break
                                else:
                                    message.append({'role': 'system', 'content': sys_prompt})
                            prompt = input(f'{colors["user"]}User: ')
                            print(f'{END}', end='')
                            if prompt == 'exit':
                                break
                            else:
                                message.append({'role': 'user', 'content': prompt})
                                chat.chat_info['history'] = chat.chat_info.get('history', []) + message
                                request_stream(chat, message, model=def_model, cost=consumption)
                        sub_com = []
                    elif sub_com[0] == 'title' and sub_com[1] == 'update':
                        update_title(chat)
                        sub_com = []
                    elif sub_com[0] == 'consumption':
                        get_consumption()
                        sub_com = []
                    else:
                        print('Chat command not recognized. Type "list commands" for further help.')
                        sub_com = []
            else:
                print('Invalid index for a chat.')
            com = []
        else:
            print('Command not recognized. Type "list commands" for further help.')
            com = []


serve()
