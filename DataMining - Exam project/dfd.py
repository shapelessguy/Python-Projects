import numpy as np
import pandas as pd
import pathlib
from os import listdir
from os.path import isfile, join
from tabulate import tabulate
import os.path
folder = str(pathlib.Path(__file__).parent.absolute()) + '/'


onlyfiles = [f for f in listdir(folder+'models') if isfile(join(folder+'/models', f))]
onlyText = [f[:len(f)-4] for f in onlyfiles if f[len(f)-3:] == 'txt']
configuration = {f: pd.read_csv('models/'+f+'.txt', sep=';') for f in onlyText}
best = {f: np.min(np.nan_to_num(configuration[f]['test_loss'].values, nan=10**10)) for f in onlyText}

best = {f: pd.DataFrame(configuration[f].values[configuration[f]['test_loss'].values == best[f]],
                        columns=configuration[f].columns) for f in onlyText}

for k, v in best.items():
    print(str(k) + ':  ' + tabulate(v, headers='keys', tablefmt='psql'), end='\n\n')

