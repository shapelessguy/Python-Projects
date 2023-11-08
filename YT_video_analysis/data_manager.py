import pandas as pd
import numpy as np
import os


def clean_lines(lines):
    n_lines = []
    for line in lines:
        line = line[line.index('>') + 1: line.rfind('<')]
        n_lines.append(line)
    return n_lines


def get_playlist(path, playlist):
    with open(path, 'r', encoding='utf8') as file:
        text = file.readlines()
    blocks, in_block = [], True
    for line in text:
        line = line.replace('\n', '')
        if line[:4] == '<td ':
            if in_block:
                blocks[-1].append(line)
            else:
                blocks.append([line])
            in_block = True
        else:
            in_block = False
    blocks = np.array([clean_lines(x) + [playlist] for x in blocks if len(x) == 5])
    blocks = pd.DataFrame(blocks, columns=['date', 'link', 'channel', 'title', 'description', 'playlist'])
    return blocks


def get_data():
    data_folder = 'data'
    files = [(os.path.join(data_folder, x), x.replace('.xls', '')) for x in os.listdir(data_folder)]
    data = {}
    for path, name in files:
        data[name] = get_playlist(path, name)
    print(data)
    return None
