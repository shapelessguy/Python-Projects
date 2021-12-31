import uproot

import sklearn as sklearn
import keras
import tensorflow
from keras import backend as K
import numpy as np
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten
from keras.layers import Conv2D, MaxPooling2D
from keras.optimizers import SGD
import os
import struct
import numpy as np
from keras.models import Sequential
from keras.layers import Dense, Dropout
import matplotlib.pyplot as plt

from keras.layers import Embedding
from keras.layers import LSTM

from keras.models import Sequential,Model
from keras.layers.core import Dense, Activation
from keras.layers import BatchNormalization, Dropout, GRU, concatenate, SimpleRNN, Masking, RNN, LSTM,Input

MaskValue = -99.0
nVariablesRNN = 4
def BuildTestRNN(Xjet_train, DimRetSeqLayers = 25, DimNORetSeqLayers = 25, dropout1 = 0.3, dropout2 = 0.3, Params = 1, activation='sigmoid'):
    print('Building Simple RNN model')

    JET_SHAPE = Xjet_train.shape[1:]

    jet_input = Input(JET_SHAPE)
    jet_channel = Masking(mask_value=MaskValue, name='jet_masking')(jet_input)

    for i in range(0, Params):
        LayerCounter1 = 1 + i
        if i == 0:
            jet_channel = LSTM(input_dim=nVariablesRNN, output_dim=DimRetSeqLayers,
                               name='jet_lstm' + str(LayerCounter1), return_sequences=True)(jet_channel)
        else:
            jet_channel = LSTM(input_dim=DimRetSeqLayers, output_dim=DimRetSeqLayers,
                               name='jet_lstm' + str(LayerCounter1), return_sequences=True)(jet_channel)
        jet_channel = Dropout(dropout1, name='jet_dropout' + str(LayerCounter1))(jet_channel)
    LayerCounter2 = LayerCounter1 + 1
    jet_channel = LSTM(output_dim=DimNORetSeqLayers, name='jet_lstm' + str(LayerCounter2), return_sequences=False)(
        jet_channel)
    jet_channel = Dropout(dropout2, name='jet_dropout')(jet_channel)

    jet_channel = Dense(output_dim=1)(jet_channel)
    jet_channel_outputs = Activation(activation)(jet_channel)

    combined_rnn = Model(inputs=[jet_input], outputs=jet_channel_outputs)
    #combined_rnn.summary()

    return combined_rnn


def Run_dRNN(x_train, y_train, x_test, y_test, lr,
             dim_conv1, dim_conv2, dim_conv3, dim_conv4,
             filter1, filter2, filter3, filter4,
             drop1, drop2, drop3, dense1,
             act1="relu", act2="relu", act3="relu", act4="relu", act5="relu", act6="softmax", epochs=6):
    model = Sequential()

    model.add(Conv2D(filter1, (dim_conv1, dim_conv1), activation=act1, input_shape=(28, 28, 1)))
    dim = 28 - dim_conv1+1
    model.add(Conv2D(filter2, (dim_conv2, dim_conv2), activation=act2))
    dim += 1 - dim_conv2
    model.add(MaxPooling2D(pool_size=(2, 2)))
    dim = (int)(dim/2)
    #print(model.output.shape)
    model.add(Dropout(drop1))

    if(dim>dim_conv3):
        model.add(Conv2D(filter3, (dim_conv3, dim_conv3), activation=act3))
        dim += 1 - dim_conv3
    if(dim>dim_conv4):
        model.add(Conv2D(filter4, (dim_conv4, dim_conv4), activation=act4))
        dim += 1 - dim_conv4
    if(dim>=2): model.add(MaxPooling2D(pool_size=(2, 2)))    #Output: (3,3,64)
    model.add(Dropout(drop2))

    model.add(Flatten())
    model.add(Dense(dense1, activation=act5))
    model.add(Dropout(drop3))
    model.add(Dense(24, activation=act6))


    sgd = SGD(lr=lr, decay=1e-6, momentum=0.9, nesterov=True)
    model.compile(loss='categorical_crossentropy', optimizer=keras.optimizers.Adadelta(), metrics=['accuracy'])

    model.fit(x_train, y_train, batch_size=32, epochs=epochs, verbose=1)

    score = model.evaluate(x_test, y_test, batch_size=32)
    print('Test loss: ', score[0])
    print('Test accuracy: ', score[1])
    keras.backend.clear_session()
    return score
