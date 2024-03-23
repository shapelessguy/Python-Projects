from matplotlib import pyplot as plt
import pandas as pd
import numpy as np


df1 = pd.read_csv('tokens-eval.csv').to_numpy()[:, :2]
df2 = pd.read_csv('tokens-input-eval.csv').to_numpy()

plt.plot(df2[:, 0], df2[:, 1])
plt.title('Response time against input tokens')
plt.xlabel('input_length')
plt.ylabel('computation_time (s)')
plt.show()
