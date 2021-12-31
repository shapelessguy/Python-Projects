from sklearn.utils import shuffle
import numpy as np
import random
random.seed(0)

n = 10
m = 10
matr = np.arange(n)
M = np.array([shuffle(matr, random_state=random.randint(0, 1000)) for i in range(m)])
print(M)