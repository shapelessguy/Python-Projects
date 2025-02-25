import datetime
import random
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import math
import io
import os
import time
import threading
import subprocess
from utils import STOCK_DB_PATH


WINDOW_LENGTH = int(datetime.timedelta(days=1).total_seconds())


class CircularBuffer:
    def __init__(self, size, dtype):
        self.size = size
        self.buffer = np.zeros(size, dtype=dtype)
        self.index = 0
        self.last_value = None
        self.busy = False

    def add(self, value):
        while self.busy:
            time.sleep(0.01)
        self.last_value = value
        self.buffer[self.index] = value
        self.index = (self.index + 1) % self.size

    def get_array(self):
        return np.roll(self.buffer, -self.index)


class Stock:
    def __init__(self, name, signal):
        self.name = name
        self.signal = signal
        self.timestamps = CircularBuffer(WINDOW_LENGTH, dtype=datetime.datetime)
        self.values = CircularBuffer(WINDOW_LENGTH, dtype=np.float64)
        self.current_value = 0
    
    def start_fetching(self):
        self.current_value = self.values.get_array()[-1]
        threading.Thread(target=self.fetch_data).start()
    
    def add(self, value, timestamp):
        self.timestamps.add(timestamp)
        self.values.add(value)

    def get_mean(self):
        ts, vls = self.timestamps.get_array(), self.values.get_array()
        timestamps = ts[::60]
        real_values = vls[::60]
        max_values, min_values = vls.reshape(-1, 60).max(axis=1), vls.reshape(-1, 60).min(axis=1)
        mean_values = vls.reshape(-1, 60).mean(axis=1)
        std_values = vls.reshape(-1, 60).std(axis=1)
        return timestamps, real_values, mean_values, std_values, max_values, min_values

    def draw_graph(self, show=False):
        self.busy = True
        timestamps, real_values, mean_values, std_values, max_values, min_values = self.get_mean()
        self.busy = False
        fig, ax = plt.subplots(figsize=(18, 8))

        sns.set_style("darkgrid")
        sns.lineplot(x=timestamps, y=mean_values)
        sns.lineplot(x=timestamps, y=min_values)
        sns.lineplot(x=timestamps, y=max_values)
        ax.fill_between(timestamps, mean_values - std_values / 2, mean_values + std_values / 2, 
                          color='blue', alpha=0.8, label="Std Deviation")
        ax.set_title(self.name)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.set_xlabel("Time")
        ax.set_ylabel("Values")

        img_bytes = io.BytesIO()
        plt.savefig(img_bytes, format='png', bbox_inches='tight')
        if show:
            plt.show()
        plt.close(fig)
        img_bytes.seek(0)
        return img_bytes

    def fetch_data(self):
        while not self.signal['kill']:
            now = time.time()
            sleep_time = 1 - (now % 1)
            time.sleep(sleep_time)
            self.add(self.current_value, datetime.datetime.now())
            time.sleep(0.01)


def simulate_stock(stock):
    initial_value = 100
    now = datetime.datetime.now()
    day_ago = now - datetime.timedelta(days=1)
    for x in range(WINDOW_LENGTH):
        ts = day_ago + datetime.timedelta(seconds=x)
        if random.random() > 0.2:
            stock.add(93 + 2 * random.random() * math.sin(x), ts)
        else:
            val = stock.values.last_value
            stock.add(val if val is not None else initial_value, ts)


def start_db(db_path: str, port: int):
    subprocess.run(f"""powershell -Command "mongod --dbpath '{db_path}' --port {port}" """,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=False)


def monitor_stocks(signal):
    threading.Thread(target=start_db, args=(STOCK_DB_PATH, 27000)).start()

    nvidia = Stock("NVIDIA", signal)
    simulate_stock(nvidia)

    stocks = [nvidia]
    for s in stocks:
        s.start_fetching()
    signal['stocks'] = stocks


if __name__ == "__main__":
    signal = {'kill': False}
    monitor_stocks(signal)
    time.sleep(5)
    signal['stocks'][0].draw_graph(show=True)
    time.sleep(10)
    signal['stocks'][0].draw_graph(show=True)
    signal['kill'] = True
