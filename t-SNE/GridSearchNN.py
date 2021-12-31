import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from tensorflow import keras
from keras.layers import Dense
from keras.layers import Input
import tensorflow as tf
physical_devices = tf.config.list_physical_devices('GPU')
tf.config.experimental.set_memory_growth(physical_devices[0], True)

def loss_function(y, y_hat):
    loss_value = (y - y_hat) ** 2
    return tf.reduce_mean(loss_value)


def split(x=np.array([]), y=np.array([]), target=np.array([]), random_state=42, test_size=0.3):
    x_train, x_test, y_train, y_test, target_train, target_test = train_test_split(x, y, target,
                                                                                   test_size=test_size,
                                                                                   random_state=random_state)
    return x_train, x_test, y_train, y_test, target_train, target_test


def create_model(input_shape: list, n_hidden=1, n_neurons=30, learning_rate=3e-3):
    model = keras.models.Sequential()

    options = {"input_shape": input_shape}
    for layer in range(n_hidden):
        model.add(keras.layers.Dense(n_neurons, activation="linear", **options))
    options = {}
    model.add(keras.layers.Dense(2, **options))
    optimizer = keras.optimizers.SGD(learning_rate)
    model.compile(loss=loss_function, optimizer=optimizer)
    return model


def model_fit(train_x, train_y, neurons, n_epochs, n_batch):
    model = keras.models.Sequential()
    model.add(Input(shape=(train_x.shape[1],)))
    model.add(Dense(neurons, activation='relu'))
    model.add(Dense(2, activation='linear'))

    model.compile(loss=loss_function, optimizer='adam', metrics=['mse'])
    model.fit(train_x, train_y, epochs=n_epochs, batch_size=n_batch, verbose=1)
    return model


def model_configs():
    # define scope of configs
    n_nodes = [44, 48]
    n_epochs = [150, 200]
    n_batch = [1]
    # create configs
    configs = list()
    for j in n_nodes:
        for k in n_epochs:
            for l in n_batch:
                cfg = [j, k, l]
                configs.append(cfg)
    print('Total configs: %d' % len(configs))
    return configs


def evaluate(train_x, train_y, test_x, test_y, configs):
    all_results = {}
    iteration = 1
    for config in configs:
        print(f'Iteration {iteration} of {len(configs)}: {config}')
        model = model_fit(train_x, train_y, neurons=config[0], n_epochs=config[1], n_batch=config[2])
        results = model.evaluate(test_x, test_y)
        all_results[tuple(config)] = results
        iteration += 1
    sorted_results = {k: v for k, v in sorted(all_results.items(), key=lambda item: item[1])}
    return sorted_results


def runANN():
    tsne_df = pd.read_csv('data1_train_0.8.csv', sep=';')
    tsne_columns = tsne_df.columns

    tsne_x_df = tsne_df.loc[:, :'X63']
    tsne_target_df = tsne_df.loc[:, 'target':'target']
    tsne_y_df = tsne_df.loc[:, 'Y0':'Y1']


    tsne_x = tsne_x_df.to_numpy()
    tsne_target = tsne_target_df.to_numpy()
    tsne_y = tsne_y_df.to_numpy()

    # Split in train and test sets
    X_train, X_test, Y_train, Y_test, t_train, t_test = split(tsne_x, tsne_y, tsne_target)

    #grid = model_configs()
    #opt_models = evaluate(X_train, Y_train, X_test, Y_test, grid)
    mod = model_fit(X_train, Y_train, 128, 150, 1)
    print(mod)

runANN()