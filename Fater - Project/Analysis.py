import Functions as fun
import Log
import GoodnessEstimate as GE
import tensorflow as tf
import matplotlib as mpl
import sklearn as sklearn
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
from tensorflow.keras.callbacks import EarlyStopping
import random
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
mpl.rcParams['figure.figsize'] = (8, 6)
mpl.rcParams['axes.grid'] = False

def generateData(aggregation = '7D', noise=0, target=''):
    # Definizione della finestra temporale
    window = (pd.Timestamp(year=2017, month=1, day=1), pd.Timestamp(year=2019, month=4, day=1))

    # Definizione delle bag di serie storiche
    seed = random.choice(range(20))
    series, mean, std = fun.getSeries_perProduct(dataset=fun.generateNoisedSellIn(noise=noise, seed=seed), minimumSeriesSize=20, norm=True,
                                      seasonality=aggregation, fromData=window[0], toData=window[1])

    if target != '':
        Data = series[[target]].fillna(0)
        mean = {target:mean[target]}
        std = {target:std[target]}
    else:
        Data = series.drop(columns=['Overall']).fillna(0)
        if 'Promo' in mean:
            mean.pop('Promo')
            std.pop('Promo')
    #fun.plotColumns(series)
    return Data, mean, std

def aggregate_perWeek(a, days):
    if days == 7: return a
    a = a/days
    b = np.tile(a, (days,1)).T.reshape((len(a)*days))
    b = b[:len(b)-len(b)%7].reshape((len(b)//7, 7)).sum(axis=1)
    return b

def addZeros(a, n):
    '''Add sequences of zero to a 2-dimensional numpy array along the first axis'''
    b = np.array([0 for i in range(n * a.shape[1])])
    c = np.append(a, b)
    c = c.reshape(int(len(c) / a.shape[1]), a.shape[1])
    return c

def conv1D_range(dataset, kernel_size, strides, total):
    '''
    Calculate the loss in dimensionality moving through a convolutional layer with specified
    kernel_size and strindes.
    Returns a reshaped (smaller) input dataset
    '''
    if strides == 1 and kernel_size == 1:
        return dataset
    indexes = [0]
    while indexes[-1] + kernel_size + strides <= total:
        indexes.append(indexes[-1] + strides)
    offset = total - indexes[-1] - kernel_size
    for elem in indexes:
        elem += offset
    return dataset[:, indexes]

def toActFunction(n):
    if(n<0.2): return "none"
    if(n<0.4): return "sigmoid"
    if(n<0.6): return "relu"
    if(n<0.8): return "softmax"
    else: return "tanh"

def multivariateData(dataset, start_index, end_index, history_size, target_size, mean, std, target_idx):
    '''
    Creating windows of time from dataset according to history_size (length of each time window) and target_size
    (distance of prediction)
    '''
    data = []
    labels = []
    n_variables = 1 #  in case of a univariate time series
    dataset_ = dataset.copy()   #  dataset copy destined to the label data
    while len(mean) <= dataset_.shape[1] and dataset_.shape[1] > 1:
        dataset_ = np.delete(dataset, dataset.shape[1]-1, axis=1)   #  Delete informations related to promos and other eventually..

    #  Formatting label data
    if target_idx == -1:    #  Overall case - needs all original series (without standardization)
                            #  added together in once and then standardized
        data_label = np.array([dataset_[:, i] * list(std.values())[i] + list(mean.values())[i] for i in range(dataset_.shape[1])])
        data_label_notNorm = data_label.sum(axis=0)[:, np.newaxis]
        data_label = (data_label_notNorm - mean['Overall']) / std['Overall']
    else:   #  Otherwise - selection of target series
        data_label = dataset_[:, target_idx][:, np.newaxis]
        data_label_notNorm = data_label * list(std.values())[target_idx] + list(mean.values())[target_idx]

    if len(dataset.shape) > 1:
        n_variables = dataset.shape[1]

    #  Considerations regarding sequences creation into the documentation..
    start_index = start_index + history_size
    if end_index is None:
        end_index = len(dataset) - target_size

    for i in range(start_index, end_index):
        indices = range(i - history_size, i)
        data.append(np.reshape(dataset[indices], (history_size, n_variables)))  #  Creation of history sequences
        labels.append(data_label[i - history_size + target_size: i + target_size])  #  Creation of labeled sequences
    return data, labels, data_label_notNorm

def prepareData(n_dataset, data_noise, aggregation, testProp, pastHistory, futureTarget, target_str, kernelSize,
                fake_futTarget, iterative, predict):

    def concatenateInnerelements(dataset_bag):
        '''
        Concatenates elements within every iterative set in dataset_bag into a set of lists
        Returns a tuple of these concatenated lists
        '''
        output_list = []
        for dataset in dataset_bag:
            output = []
            for element in dataset:
                output += element
            output_list.append(np.array(output))
        return tuple(output_list)

    XTrain = []
    YTrain = []
    XVal = []
    YVal = []
    XTest = []
    YTest = []
    last_seq = np.array([])
    complete_series = []

    for i in range(n_dataset):
        if i == 0: noise = 0
        else: noise = data_noise

        if not iterative:
            Data, mean, std = generateData(aggregation=aggregation, noise=noise)  #  Generate standardized data together with
                                                                                  #  mean and standard deviation (used for
                                                                                  #  compute the MSE properly)
            Data = Data.values
            if predict: Data = addZeros(Data, pastHistory)
            if target_str == 'Overall': target_idx = -1
            else: target_idx = [key for key in mean.keys()].index(target_str)   #  finds index associated with target

            # Generate sequencies of multivariate time series x and univariate time series y (target)
            x, y, data_values = multivariateData(Data, 0, None, pastHistory, futureTarget, mean, std, target_idx)
            if i == 0: complete_series = data_values    #  complete target sequence needed for the prediction

            #  Considerations regarding dimensional constraints into the documentation..
            targetLenght = pastHistory
            validation_size = targetLenght
            sum_train_test = len(Data) - 2 * targetLenght - validation_size
            if sum_train_test < 20: raise ValueError('Dataset too small')
            test_size = max(8, int(sum_train_test/3))
            test_size = 1 + (test_size-1)*testProp                  #  Resizing test set size
            train_size = sum_train_test - test_size
            if test_size == 1 and i != 0: test_size = 0

            XTrain.append(x[:train_size])
            YTrain.append(y[:train_size])
            XVal.append(x[train_size:train_size + validation_size])
            YVal.append(y[train_size:train_size + validation_size])
            XTest.append(x[train_size + validation_size:train_size + validation_size + test_size])
            YTest.append(y[train_size + validation_size:train_size + validation_size + test_size])

        else:
            # Generate standardized data together with  mean and standard deviation (used for compute the MSE properly)
            Data, mean, std = generateData(aggregation=aggregation, noise=noise, target=target_str)
            target_idx = 0
            Data = Data.values
            if predict: Data = addZeros(Data, pastHistory)
            # Generate sequencies of multivariate time series x and univariate time series y (target) for the one-step computation
            x, y, data_values = multivariateData(Data, 0, len(Data) - fake_futTarget + pastHistory-futureTarget, pastHistory,
                                                    futureTarget, mean, std, target_idx)
            if i == 0: complete_series = data_values    #  complete target sequence needed for the prediction

            left_test = futureTarget - fake_futTarget   #  sequence left for the test
            last_step = pastHistory - futureTarget
            last_Yseq = np.array([element[0] for element in y[-left_test-1:]])
            if i == 0: last_seq = last_Yseq
            y = [element[last_step:last_step + fake_futTarget + 1] for element in y[:-left_test]]
            x = x[:len(y)]

            optimalValidationSize = 8   #  if there is not so much data, at least 8 sample will work as validation
            if predict: optimalValidationSize = pastHistory    #  while predicting it is needed at least pastHistory samples
                                                               #  in order to avoid overlapping between train and test set
            # Size settings associated with the one-step ahead computation
            # .. again the details into the documentation
            targetLenght = fake_futTarget + 1
            validation_size = max(targetLenght, optimalValidationSize)
            sum_train_test = len(Data) - targetLenght - pastHistory - validation_size - left_test
            if sum_train_test < 20: raise ValueError('Dataset too small')
            test_size = max(8, int(sum_train_test / 3))
            test_size = 1 + (test_size - 1) * testProp
            train_size = sum_train_test - test_size
            if test_size == 1 and i != 0: test_size = 0

            XTrain.append(x[:train_size])
            YTrain.append(y[:train_size])
            XVal.append(x[train_size:train_size + validation_size])
            YVal.append(y[train_size:train_size + validation_size])
            if test_size>0:
                XTest.append(x[-test_size:])
                YTest.append(y[-test_size:])

    xTrain, yTrain, xVal, yVal, xTest, yTest = concatenateInnerelements((XTrain, YTrain, XVal, YVal, XTest, YTest))

    # Splitting the data between train, validation and test
    BATCH_SIZE = 120
    BUFFER_SIZE = 2400

    if not iterative:
        yTrain = conv1D_range(yTrain, kernelSize, 1, pastHistory)
        yVal = conv1D_range(yVal, kernelSize, 1, pastHistory)
        yTest = conv1D_range(yTest, kernelSize, 1, pastHistory)
        train = tf.data.Dataset.from_tensor_slices((xTrain, yTrain))
        train = train.cache().shuffle(BUFFER_SIZE).batch(BATCH_SIZE).repeat()
        validation = tf.data.Dataset.from_tensor_slices((xVal, yVal))
        validation = validation.batch(BATCH_SIZE).repeat()
    else:
        yTrain = conv1D_range(yTrain, kernelSize, 1, fake_futTarget+1)
        yVal = conv1D_range(yVal, kernelSize, 1, fake_futTarget+1)
        yTest = conv1D_range(yTest, kernelSize, 1, fake_futTarget+1)
        train = tf.data.Dataset.from_tensor_slices((xTrain, yTrain))
        train = train.cache().shuffle(BUFFER_SIZE).batch(BATCH_SIZE).repeat()
        validation = tf.data.Dataset.from_tensor_slices((xVal, yVal))
        validation = validation.batch(BATCH_SIZE).repeat()

    return xTrain, yTrain, xVal, yVal, xTest, yTest, train, validation, validation_size, mean, std, target_idx, last_seq, complete_series

def getLastSequencePrediction(iterative, model, n_dataset, xTest, yTest, mean, std, target, pastHistory, target_idx,
                              futureTarget, fake_futureTarget, days, last_seq):
    last_seq_index = int(len(xTest) / n_dataset) - 1
    x_prediction = np.array([xTest[last_seq_index]])   #  last sequence of the true dataset
    #print(len(xTest[last_seq_index]))
    prediction = model.predict(x_prediction)  # prediction on the last test sequence

    if not iterative:
        prediction = model.predict(x_prediction)  # prediction on the last test sequence
        if target == 'Overall':
            while len(mean) <= xTest.shape[2] and xTest.shape[2] > 1:  # Delete informations related to promos
                xTest = np.delete(xTest, xTest.shape[2] - 1, axis=2)  # and other eventually..
            last_xSum = np.array([xTest[last_seq_index][:, i] * list(std.values())[i] + list(mean.values())[i]
                                  for i in range(xTest[last_seq_index].shape[1])]).sum(axis=0)
        else:
            last_xSum = np.array(xTest[last_seq_index][:, target_idx]) * list(std.values())[target_idx] + \
                        list(mean.values())[target_idx]
        firstPoints = np.reshape(last_xSum[:futureTarget], min(futureTarget, len(last_xSum)))
        #  last_xSum is the the sequence that precedes the target one
        #  firstPoints is the sequence that precedes entirely the target one
        prediction = np.reshape(prediction, (prediction.shape[1],)) * std[target] + mean[
            target]  # prediction unstandardized

        # real data associated with the prediction unstandardized
        real = np.array([yTest[last_seq_index] * std[target] + mean[target]])[-futureTarget:].reshape(yTest.shape[1])

        if fake_futureTarget != 0:  # Eventually removing the fake_futureTarget used as ploy for Conv1D
            real = real[:-fake_futureTarget]
            prediction = prediction[:-fake_futureTarget]
        real = real[pastHistory-futureTarget:]
        prediction = prediction[pastHistory-futureTarget:]

    else:
        prediction_seq = []
        for i in range(futureTarget-fake_futureTarget):
            prediction_seq.append(model.predict(x_prediction))
            x_prediction = list(x_prediction.reshape((x_prediction.shape[1])))[1:]
            predicted = prediction_seq[-1]
            if predicted < 0: predicted = 0
            x_prediction.append(predicted)
            x_prediction = np.array(x_prediction, dtype=np.float32).reshape((1,len(x_prediction),1))

        prediction = np.array(prediction_seq).reshape((len(prediction_seq))) * list(std.values())[target_idx] + \
                        list(mean.values())[target_idx]
        firstPoints = xTest.reshape((xTest.shape[1])) * list(std.values())[target_idx] + list(mean.values())[target_idx]
        real = last_seq.reshape((len(last_seq)))[-len(prediction_seq):] * list(std.values())[target_idx] + list(mean.values())[target_idx]

    print('History lenght: {}  -  Prediction lenght: {}'.format(pastHistory, len(prediction)))
    mse = np.power(real - prediction, 2).sum() / (len(real) * 100000)  # MSE computed on the very last sequence

    firstPoints = aggregate_perWeek(firstPoints, days)  # Re-aggregate per week in case of dissimilar
    real = aggregate_perWeek(real, days)  # dataset aggregation
    prediction = aggregate_perWeek(prediction, days)

    # MSE computed on the very last sequence and per week
    mse_week = np.power(real - prediction, 2).sum() / (len(real) * 100000)
    return firstPoints, real, prediction, mse, mse_week


def runGRU(hyperparameters, target:str, n_dataset=10, noise=3, goodness='last', iterative=True,
           saveGraph=False, saveLog=False, predict=None, verbose=0):

    aggregation, pastHistory_fac, testProp, epochs, kernelSize, dilations, dropout, conv1_filters, conv2_filters, n1, n2, activation = hyperparameters
    if iterative: pastHistory_fac = 0

    if type(aggregation) == str: aggregation = fun.conversion(aggregation)  #  aggregation can be a string '1D', '2D' ..
    parameters = (aggregation, ) + hyperparameters[1:]                           #  ..this converts it to a float in [0,1]
    if type(aggregation) != str: aggregation = fun.conversion(aggregation)  #  from now on it will be a string

    act = activation
    if type(act) != str: act = toActFunction(act)    #  converts the activation float into a string
    if act == 'none': act = None                     #  or eventually into None
    testProp = int(testProp)
    epochs = int(epochs)
    kernelSize = int(kernelSize)
    dilations = int(dilations)
    conv1_filters = int(conv1_filters)
    conv2_filters = int(conv2_filters)
    n1 = int(n1)
    n2 = int(n2)

    day_aggregation = int(aggregation[0])   #  number of days used by the dataset aggregation
    true_futureTarget = int(180/day_aggregation)    #  6 month target in terms of steps to predict
    futureTarget = true_futureTarget# + kernelSize - 1      #  steps number in case of a kernel size > 1 in order to keep
                                                           #  ..time predictions up to 6 months (technical reasons)
    fake_futureTarget = futureTarget - true_futureTarget

    pastHistory = int(futureTarget + pastHistory_fac*futureTarget)  #  pastHistory fac expresses itself as a factor
                                                                    #  of futureTarget (oscillate between the latter and
                                                                    #  (pastHistory_fac+1) times it)

    xTrain, yTrain, xVal, yVal, xTest, yTest, train, validation, validationLen, mean, std, target_idx, last_seq, \
    complete_series = prepareData(n_dataset, noise, aggregation, testProp, pastHistory, futureTarget, target, kernelSize,
                    fake_futureTarget, iterative, predict)


    def futureMSE(yTrue, yPred):
        if not iterative:
            startPoint = -futureTarget
            y_true = yTrue[startPoint:] * std[target] + mean[target]
            y_pred = yPred[startPoint:] * std[target] + mean[target]
        else:
            y_true = yTrue * std[target] + mean[target]
            y_pred = yPred * std[target] + mean[target]
        return tf.keras.metrics.mean_squared_error(y_true, y_pred)/100000

    evaluation_interval = 50
    # RNN (with GRUs) model definition
    try:
        model = tf.keras.models.Sequential()
        returnSeq = True
        if dilations != 0:
            for rate in [2 ** i for i in range(dilations)] * 2:
                model.add(tf.keras.layers.Conv1D(filters=conv1_filters, kernel_size=2, padding="causal",
                                                 activation="relu", dilation_rate=rate,
                                                 input_shape=[None, xTrain.shape[2]]))
        if kernelSize != 1:
            model.add(tf.keras.layers.Conv1D(filters=conv2_filters, kernel_size=kernelSize, padding="valid",
                                             input_shape=[xTrain.shape[1], xTrain.shape[2]]))
        if n2 == 0 and iterative: returnSeq = False
        model.add(tf.keras.layers.GRU(n1, return_sequences=returnSeq, recurrent_dropout=dropout, input_shape=[None, xTrain.shape[2]]))
        model.add(tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(futureTarget)))
        if n2 != 0:
            if iterative: returnSeq = False
            model.add(tf.keras.layers.Dropout(dropout))
            model.add(tf.keras.layers.GRU(n2, return_sequences=returnSeq, recurrent_dropout=dropout))
        if not iterative: model.add(tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(futureTarget)))
        model.add(tf.keras.layers.Dense(1, activation=act))

        model.compile(optimizer='adam', loss='mse', metrics=[futureMSE])
        if epochs != 0: es = []
        else:
            epochs = 100
            es = [EarlyStopping(monitor='val_futureMSE', mode='min', verbose=1)]

        model_oneStep = tf.keras.models.clone_model(model)    #  Creating an identical model to test the one-step approach
        model_oneStep.compile(optimizer='adam', loss='mse', metrics=[futureMSE])

        if verbose:
            print('------TRAIN------')
            print('X: {} - Y: {}'.format(xTrain.shape, yTrain.shape))
            print('------TEST------')
            print('X: {} - Y: {}'.format(xTest.shape, yTest.shape))

        #  Fitting the model
        print('Fitting: {} ...'.format(parameters), end='')
        history = model.fit(train, epochs=epochs, steps_per_epoch=evaluation_interval, validation_data=validation,
                            validation_steps=min(validationLen, 40), verbose=verbose, callbacks=[es])

        #  Testing the model
        print(' Evaluating ... ', end='')
        test_score = model.evaluate(xTest, yTest, batch_size=min(len(xTest), 40), verbose=verbose)

        avgMSE = test_score[1]    #  average MSE computed on test set sequences

        firstPoints, real, prediction, mse, mse_week = \
            getLastSequencePrediction(iterative, model, n_dataset, xTest, yTest, mean, std, target, pastHistory,
                                      target_idx, futureTarget, fake_futureTarget, day_aggregation, last_seq)

        if predict:
            firstPoints = complete_series[:-pastHistory]

        if saveGraph:
            plt.clf()
            fig, axis = plt.subplots(1, figsize=(20, 10))
            title = '{} -> avg_mse={}, last_mse={}, epochs={}'.format(target, avgMSE, mse, epochs)
            if predict:
                title = '{}'.format(target)
                axis.plot(list(range(len(firstPoints))), list(firstPoints), color='black', label='Real data')
            else:
                axis.plot(list(range(len(real) + len(firstPoints))), list(firstPoints) + list(real), color='black', label='Real data')
            axis.plot(list(range(len(real) + len(firstPoints)))[len(firstPoints):], list(prediction), color='red',
                      label='Predicted data', linewidth=3)
            axis.set_title(title)
            axis.legend(loc='best')
            name = 'Plots/{}_lastMse_{:.3f}_avgMse_{:.3f}.png'.format(target, mse, avgMSE)
            if predict: name = 'Predictions/{}'.format(target)
            fig.savefig(name)
            plt.close(fig)
        if predict:
            return list(prediction)

        #if mse_onLast:  #  if mse_onLast is True, the goodness of prediction is given by the only last sequence
        if goodness == 'last': goodness = mse
        elif goodness == 'last_week': goodness = mse_week
        elif goodness == 'avg_test': goodness = avgMSE
        else: raise AttributeError('Select one of the goodness choices: last, last_week, avg_test')

        #  Log creation
        log = Log.log(((goodness, avgMSE, mse, mse_week), epochs, evaluation_interval, target,
                                    GE.prediction(history.history['val_loss']), parameters))
        if saveLog:
            with open("logs.txt", "a+") as file: file.write(log.serialize() + '\n') #  Save log on hard disk
        log.print()
        try: tf.keras.backend.clear_session()      #  close keras backend to free the RAM
        except Exception: print("Can't clear keras session")
        return log
    except Exception as ex:
        print(ex)
        log = Log.log(((100, ), epochs, evaluation_interval, target, [0,0,0], parameters))
        if saveLog:
            with open("logs.txt", "a+") as file: file.write(log.serialize() + '\n') #  Save log on hard disk even in exception
        print('Exception: {}'.format(parameters))
        try: tf.keras.backend.clear_session()
        except Exception: print("Can't clear keras session")
        return log


def singleRun():
    fun.initializeDatasets()
    aggregation = 0.99
    pastHistory = 0.0
    testProp = 0
    epochs = 7
    kernelSize = 2
    dilations = 0
    dropout = 0.7
    conv1_filters = 30
    conv2_filters = 30
    n1 = 20
    n2 = 20
    activation = 0.0
    parameters = (aggregation, pastHistory, testProp, epochs, kernelSize, dilations, dropout, conv1_filters, conv2_filters, n1, n2, activation)
    #parameters = ('7D', 0.000, 0.290, 6.000, 1.000, 2.000, 0.290, 11.000, 8.000, 44.000, 43.000, 0.842)
    parameters = ('7D', 0.000, 0, 10, 6.000, 3.000, 0.181, 33.000, 7.000, 11.000, 27.000, 0)
    output = runGRU(hyperparameters=parameters, target='Product 9', goodness='last', n_dataset=10, noise=3,
           iterative=True, saveGraph=True, verbose=1, predict=True)

if __name__ == '__main__':
    singleRun()
