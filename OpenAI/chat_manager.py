import os
import json
import time


class Chat:
    def __init__(self, dir_path, chat_info, index=0):
        self.dir_path = dir_path
        now = time.time()
        self.chat_info = chat_info if chat_info is not None else {
            'created': now,
            'last_update': now,
            'title': "No title.",
            'last_title_update': now,
            'index': index,
            'history': []
        }
        self.index = self.chat_info['index']

    def delete(self):
        if os.path.exists(self.dir_path):
            os.remove(self.dir_path)
            print(f'Chat {self.index} at {self.dir_path} has been deleted.')
        else:
            print(f'Chat {self.index} has been deleted.')

    def save(self, update=True):
        now = time.time()
        if update:
            self.chat_info['last_update'] = now
        with open(self.dir_path, 'w') as file:
            json.dump(self.chat_info, file)

    def __str__(self):
        return f'ID: {self.index}  - ' \
            f'created: {time.strftime("%d-%m-%Y %H:%M:%S", time.localtime(self.chat_info["created"]))}  ' \
            f'last update: {time.strftime("%d-%m-%Y %H:%M:%S", time.localtime(self.chat_info["last_update"]))}' \
            f' - Summary: {self.chat_info["title"]}'


def new_chat(chat_dir):
    chats = [int(x[:-5]) for x in os.listdir(chat_dir)]
    n_chat_index = (max(chats) + 1) if len(chats) > 0 else 0
    chat_path = os.path.join(chat_dir, str(n_chat_index) + '.json')
    return Chat(chat_path, None, index=n_chat_index)


def get_all_chats(chat_dir):
    chats = os.listdir(chat_dir)
    all_chats = []
    for chat in chats:
        chat_path = os.path.join(chat_dir, chat)
        with open(chat_path, 'r') as file:
            all_chats.append(Chat(chat_path, json.load(file)))
    return sorted(all_chats, key=lambda x: x.index)
