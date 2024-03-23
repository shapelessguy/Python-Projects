import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import date, timedelta
start_date = date(2023, 6, 1)
end_date = date(2023, 11, 16)
file_path = r"C:\Users\shape\Documents\Bureaucracy\WG\Cleanings.xlsx"


def to_integer(dt_time):
    return 100*dt_time.month + dt_time.day


def moving_average(a, n=3):
    ret = np.cumsum(a, axis=0, dtype=float)
    ret[n:, :] = ret[n:, :] - ret[:-n, :]
    return ret[n - 1:, :] / n


df = pd.read_excel(file_path, sheet_name='Dishwasher').iloc[35:, 1:7].to_numpy().T
names = df[:, 0]
values = df[:, 1:]
values = {n: [i.date() for i in l_ if not pd.isna(i)] for n, l_ in zip(names, values)}
int_values = []

sds = start_date.strftime("%Y%m%d")
eds = start_date.strftime("%Y%m%d")

delta = end_date - start_date   # returns timedelta

for i in range(delta.days + 1):
    day = start_date + timedelta(days=i)
    int_value = []
    for n in values:
        int_value += [0]
        for v in values[n]:
            if day == v:
                int_value[-1] += 1
    int_values += [int_value]

time_range = [start_date + timedelta(days=x) for x in range(len(int_values))]
if not os.path.exists(f'{sds}_{eds}'):
    os.mkdir(f'{sds}_{eds}')

plt.figure(figsize=(12, 8), dpi=80)
plt.title(f'Cumulative unloadings throughout time')
df = pd.DataFrame(np.array(int_values).cumsum(axis=0).sum(axis=1), columns=['Tot'])
df.index = time_range
sns.lineplot(data=df)
plt.plot([start_date, end_date], [0, delta.days])
plt.tight_layout()
plt.savefig(f"{sds}_{eds}\\plt1.png", dpi=200)

plt.figure(figsize=(12, 8), dpi=80)
plt.title(f'Cumulative unloadings throughout time per person')
df = pd.DataFrame(np.array(int_values).cumsum(axis=0), columns=names)
df.index = time_range
sns.lineplot(data=df)
plt.tight_layout()
plt.savefig(f"{sds}_{eds}\\plt2.png", dpi=200)

average_n_days = 30
time_range = time_range[average_n_days - 1:]

fig, axs = plt.subplots(len(names), figsize=(12, 8))
fig.suptitle(f'Number of unloadings per day, averaged in {average_n_days} days')
average = moving_average(int_values, n=average_n_days)
df = pd.DataFrame(average, columns=names)
df.index = time_range
max_speed = df.max().to_numpy().max()
for name, i in zip(names, range(len(names))):
    sns.lineplot(data=df[name], ax=axs[i])
    axs[i].set_ylim(0, max_speed)
    axs[i].text(start_date + timedelta(days=25), max_speed * 0.83, f'avg: {round(df[name].mean(), 2)}', fontsize=10)
plt.tight_layout()
plt.savefig(f"{sds}_{eds}\\plt3.png", dpi=200)

plt.figure(figsize=(12, 8), dpi=80)
plt.title(f'Number of unloadings per day, averaged in {average_n_days} days')
df = pd.DataFrame(average.sum(axis=1), columns=['Tot'])
df.index = time_range
sns.lineplot(data=df)
plt.tight_layout()
plt.savefig(f"{sds}_{eds}\\plt4.png", dpi=200)


