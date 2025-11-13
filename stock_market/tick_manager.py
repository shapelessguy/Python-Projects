import yfinance as yf
import matplotlib.pyplot as plt
import datetime as dt
import pytz
import pandas as pd
from collections import deque
import itertools
import time

tz = pytz.timezone("Europe/Berlin")


PHASES = [
    # {"period": 7, "interval": 1},
    {"period": 30, "interval": 2},
    # {"period": 60, "interval": 15},
    {"period": 730, "interval": 60},
    {"period": 365 * 50, "interval": 1440},
]



FREQ_MAP = {
    '5T': 1,
    '30T': 7,
    '1H': 30,
    '6H': 60,
    '12H': 120,
    '1D': 365,
    '2D': 730,
    '5D': 365 * 50
}


class Window:
    def __init__(self, window, phase):
        self.window: deque = window
        self.phase = phase
        self.window_bound = [None, None]
        self.update_min_max_date()
    
    def update_min_max_date(self):
        self.window_bound = [self.window[0][0], self.window[-1][0]]
    
    def insert(self, value, cur_time, prev_min_ts):
        if self.window_bound[1] + dt.timedelta(minutes=self.phase['interval']) < prev_min_ts:
            self.window.append((cur_time, value))
            self.update_min_max_date()
            return True
        return False


class Windows:
    def __init__(self, window_list: list[deque]):
        self.window_list = window_list
    
    def get_concatenated(self):
        return list(itertools.chain.from_iterable([w.window for w in self.window_list[::-1]]))
    
    def get_formatted(self, freq):
        now = tz.localize(dt.datetime.now())
        stop_at = now - dt.timedelta(days=FREQ_MAP[freq])
        data = []
        stop = False
        off_times = []
        prev_off_time = now
        compute_on = FREQ_MAP[freq] <= 30
        for w in self.window_list:
            for t, v in reversed(w.window):
                if t < stop_at:
                    stop = True
                if stop:
                    break
                if v > 0:
                    # Dates: decreasing order
                    if prev_off_time - t > dt.timedelta(hours=6) and compute_on:
                        off_times.append((t, prev_off_time))
                    prev_off_time = t
                    dp = {"time": t, "value": v}
                    data.insert(0, dp)
            if stop:
                break
        df = pd.DataFrame(data)
        df.set_index('time', inplace=True)
        df.sort_index(inplace=True)
        df_resampled = df.resample(freq).mean().interpolate()
        result = df_resampled.reset_index().to_dict('records')

        off_interval_idx = 0
        for s in result:
            for i in range(off_interval_idx, len(off_times) - 1):
                if s["time"] < off_times[i][0]:
                    off_interval_idx += 1
            if len(off_times):
                s["type"] = "overnight" if (off_times[off_interval_idx][0] <= s["time"] <= off_times[off_interval_idx][1]) else ""
            else:
                s["type"] = ""
        print(off_times)
        for r in result:
            print(r)
        return result
    
    def insert(self, value):
        cur_time = tz.localize(dt.datetime.now())
        prev_min_ts = cur_time
        for w in self.window_list:
            inserted = w.insert(value, cur_time, prev_min_ts)
            prev_min_ts = w.window_bound[0]
            if not inserted:
                break
    
    def plot(self, from_days_prior=30):
        from_time = tz.localize(dt.datetime.now() - dt.timedelta(days=from_days_prior))
        df = pd.DataFrame(self.get_concatenated(), columns=["Datetime", "Value"]).set_index("Datetime")
        filtered = df[(df.index >= from_time)]
        filtered.plot()
        plt.title("Stock name")
        plt.xlabel("Time")
        plt.ylabel("Price")
        plt.show()
        print("OK")


def initialize_windows(stock_symbol):
    stock_ticker = yf.Ticker(stock_symbol)
    windows = []
    filtered = None
    now_tz = tz.localize(dt.datetime.now())

    dfs = []
    for i, ph in enumerate(PHASES):
        period_str = f"{ph['period']}d" if ph['period'] < 999999 else "max"
        interval_str = f"{ph['interval']}m" if ph['interval'] < 1000 else "1d"
        df = stock_ticker.history(period=period_str, interval=interval_str)["Close"]
        dfs.append(df)

    for i, ph in enumerate(PHASES):
        end_time = filtered.index[0] if filtered is not None else now_tz
        start_time = now_tz - dt.timedelta(days=ph['period'])
        df = dfs[i]
        filtered_ = df[(df.index >= start_time) & (df.index < end_time)]
        
        WINDOW_SIZE = max(len(filtered_), 5000)
        if len(filtered_) < 2:
            continue

        if len(filtered_) < WINDOW_SIZE and (sum([len(d) for d in dfs[i:]]) == 0):
            repeats = WINDOW_SIZE - len(filtered_)
            min_index = min(filtered_.index[0], end_time)
            timestamps = [min_index - pd.Timedelta(minutes=ph["interval"] * i) for i in range(repeats, 0, -1)]
            padding = pd.DataFrame({"Close": [0] * repeats}, index=timestamps)
            filtered_ = pd.concat([padding, filtered_])["Close"]

        filtered = filtered_
        windows.append(Window(deque(zip(filtered.index.to_pydatetime(), filtered.tolist()), maxlen=WINDOW_SIZE), ph))

    return Windows(windows)


windows = initialize_windows("CSSPXM.XD")
windows.get_formatted("1D")
# windows.plot(365)
# for _ in range(100):
#     windows.insert(1)
# while True:
#     windows.insert(2)
#     time.sleep(1)
