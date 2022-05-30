import pandas as pd
import numpy as np
import seaborn as sns
from matplotlib import pyplot as plt


def get_conversion_tables():
    with open('conversion_tables.txt', 'r') as file:
        lines = file.readlines()

    tables = []
    block = []
    for line in lines:
        line = line.replace('\n', '')
        if line == '':
            tables.append(block)
            block = []
        else:
            block.append(line)
    if len(block) > 1:
        tables.append(block)
    for i in range(len(tables)):
        tables[i] = ConversionTable(tables[i])
    return tables


class ConversionTable:
    def __init__(self, lines):
        self.title = lines[0].upper()
        self.columns = lines[1].split('\t')
        self.values = []
        for l in lines[2:]:
            self.values.append([x if len(x) > 0 else 0 for x in l.split('\t')])
        self.values = np.array(self.values, dtype=int)

    def get_df(self):
        return pd.DataFrame(self.values, columns=self.columns)

    def __str__(self):
        string = f'{self.title}\n'
        string += str(pd.DataFrame(self.values, columns=self.columns)) + '\n'
        return string


class Conversion:
    def __init__(self, tables):
        self.tables = tables

    @staticmethod
    def find_segment_index(array, value):
        segment_index = 0
        for i in range(0, len(array)):
            segment_index = i
            if array[i] < value:
                continue
            else:
                break
        segment_index = 1 if segment_index < 1 else segment_index
        segment_index = len(array) if segment_index > len(array) else segment_index
        return segment_index

    def translate(self, array1, array2, value):
        segment_index = self.find_segment_index(array1, value)
        x0, x1 = array1[segment_index-1], array1[segment_index]
        y0, y1 = array2[segment_index-1], array2[segment_index]
        translated_value = (value-x0)/(x0-x1) * (y0-y1) + y0
        return translated_value

    def chess_to_lichess(self, speed, value):
        if speed == 'classical':
            speed = 'rapid'
        table_chess = [t.get_df() for t in self.tables if t.title == 'CHESS.COM'][0]
        table_lichess = [t.get_df() for t in self.tables if t.title == 'CHESS.COM TO LICHESS'][0]
        perfect4 = ['bullet', 'blitz', 'rapid', 'classical']
        if speed not in perfect4:
            return None
        speed1 = 'ChessBlitz' if speed == 'blitz' else speed.title()
        speed = speed.title()
        conv_flow = [table_chess[speed1], table_chess['ChessBlitz'], table_lichess['ChessBlitz'], table_lichess[speed]]
        conv_flow = [x.values for x in conv_flow]

        chess_blitz_value = self.translate(conv_flow[0], conv_flow[1], value)
        lichess_value = self.translate(conv_flow[2], conv_flow[3], chess_blitz_value)
        return int(lichess_value)
