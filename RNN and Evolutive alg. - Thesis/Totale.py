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
import os
import pickle
import matplotlib.pyplot as plt

import pandas as pd
import sklearn as sklearn
import numpy as np
import json

from keras.callbacks import ModelCheckpoint, EarlyStopping

from keras.optimizers import Adam
from pip._vendor.colorama import Fore, Back
import uproot

nVariablesRNN = 4
DimRetSeqLayers = 25
DimNORetSeqLayers = 25
dropout = 0.3
Params = 1
MaskValue = -99.0


def BuildTestRNN(Xjet_train):
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
        jet_channel = Dropout(dropout, name='jet_dropout' + str(LayerCounter1))(jet_channel)
    LayerCounter2 = LayerCounter1 + 1
    jet_channel = LSTM(output_dim=DimNORetSeqLayers, name='jet_lstm' + str(LayerCounter2), return_sequences=False)(
        jet_channel)
    jet_channel = Dropout(dropout, name='jet_dropout')(jet_channel)

    jet_channel = Dense(output_dim=1)(jet_channel)
    jet_channel_outputs = Activation('sigmoid')(jet_channel)

    combined_rnn = Model(inputs=[jet_input], outputs=jet_channel_outputs)
    combined_rnn.summary()

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


path = 'FlatTree'

LearningRate = 0.001
BatchSize = 4096

def run_Training(X_train, y_train):
    model = BuildTestRNN(X_train)
    model.compile(optimizer=Adam(lr=LearningRate), metrics=['accuracy'], loss='binary_crossentropy')

    print(Fore.BLUE + "--------------------------")
    print(Back.BLUE + "       TRAINING RNN       ")
    print(Fore.BLUE + "--------------------------")
    try:
        modelMetricsHistory = model.fit([X_train], y_train, batch_size=BatchSize,
                                        verbose=False,
                                        callbacks=[
                                        EarlyStopping(verbose=False, patience=10, monitor='val_loss'),

                                        ModelCheckpoint(path + '/model.h5', monitor='val_loss', verbose=False,
                                                        save_best_only=True)

                                        ],
                                        epochs=200,
                                        validation_split=0.2)
    except NameError:
        print('bo')
    return model

path = 'FlatTree'
listFiles = ['FlatTree_VBFH1000_spin0.root', 'FlatTree_ggFH1000_spin0.root']
rootBranchSubSample = ['Jet1_pt', 'Jet1_eta', 'Jet1_phi', 'Jet1_E',
        'Jet2_pt', 'Jet2_eta', 'Jet2_phi', 'Jet2_E',
        'Jet3_pt', 'Jet3_eta', 'Jet3_phi', 'Jet3_E',
        'Jet4_pt', 'Jet4_eta', 'Jet4_phi', 'Jet4_E',
       'Jet5_pt', 'Jet5_eta', 'Jet5_phi', 'Jet5_E',
        'Jet6_pt', 'Jet6_eta', 'Jet6_phi', 'Jet6_E']


diviso = 1
ridotto=True

DF = pd.DataFrame()
i=0
for fileInDir in listFiles:
    flatNtuple = path + '/' + fileInDir
    print(flatNtuple)
    if os.path.isfile(flatNtuple):
        i+=1
        theFile = uproot.open(flatNtuple)
        theTree = theFile.keys()
        tree = uproot.open(flatNtuple)[theTree[0]]
        DF = tree.pandas.df(rootBranchSubSample)
        DF = DF[DF['Jet1_pt']>0]
        if(i==1):
            DF['type'] = 1
        else:
            DF['type'] = 0
        N_events = DF.shape[0]
        if(i==1):
            VBF=DF
        else:
            ggF=DF

'''
lista_vbf=[]
VBF=VBF['Jet1_eta']
for i in VBF:
    print(i)
    lista_vbf.append(i)
lista_ggf=[]
for i in ggF['Jet1_eta']:
    lista_ggf.append(i)


plt.hist(lista_vbf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram vbf")
plt.show()

plt.hist(lista_ggf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram ggf")
plt.show()
'''

DF=VBF.append(ggF)
DF = sklearn.utils.shuffle(DF,random_state=123) #'123' is the random seed
'''
print(DF.shape)
lista_vbf=[]
DF1=DF[DF['type']==1]
DF1=DF1['Jet1_eta']
DF2=DF[DF['type']==0]
DF2=DF2['Jet1_eta']
for i in DF1:
    lista_vbf.append(i)
lista_ggf=[]
for i in DF2:
    lista_ggf.append(i)

print(len(lista_vbf))
print(len(lista_ggf))
plt.hist(lista_vbf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram vbf")
plt.show()

plt.hist(lista_ggf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram ggf")
plt.show()
'''

VariablesRNN = ['pt', 'eta', 'phi', 'E']

y = DF['type']
lista=[]
for i in y:
    lista.append(i)

y=lista
y_train = []
y_test = []
DF = DF[rootBranchSubSample]

if (ridotto): N_events = (int)(DF.shape[0] / diviso)
train = DF[:(int)(N_events * 0.7)]
y_train = y[:(int)(N_events * 0.7)]
test = DF[(int)(N_events * 0.7):N_events]
y_test = y[(int)(N_events * 0.7):N_events]


MaskValue = -99.
nVariablesRNN = 4
nTimeStepsRNN = 6

new_train = np.zeros((train.shape[0], nTimeStepsRNN, nVariablesRNN))
new_test = np.zeros((test.shape[0], nTimeStepsRNN, nVariablesRNN))


for i in range(0, train.shape[0]):
    for j in range(0, train.shape[1]):
        new_train[i, int(j/nVariablesRNN), j%nVariablesRNN] = train.iloc[i, j]
train = new_train

for i in range(0, test.shape[0]):
    for j in range(0, test.shape[1]):
       new_test[i, int(j/nVariablesRNN), j%nVariablesRNN] = test.iloc[i, j]
test = new_test

'''
lista_vbf=[]
lista_ggf=[]
for i, j in zip(train, y_train):
    if(j==1): lista_vbf.append(i[0][1])
    else: lista_ggf.append(i[0][1])

plt.hist(lista_vbf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram vbf")
plt.show()

plt.hist(lista_ggf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram ggf")
plt.show()
'''

def scale(data, var_names, savevars, VAR_FILE_NAME='scaling'):
    '''
    Args:
    -----
        data: a numpy array of shape (nb_events, nb_particles, n_variables)
        var_names: list of keys to be used for the model
        savevars: bool -- True for training, False for testing
                  it decides whether we want to fit on data to find mean and std
                  or if we want to use those stored in the json file

    Returns:
    --------
        modifies data in place, writes out scaling dictionary
    '''
    # import json

    modelpath = path

    scale = {}
    if savevars:
        for v, name in enumerate(var_names):
            print('Scaling feature %s of %s (%s).' % (v + 1, len(var_names), name))
            f = data[:, :, v]
            slc = f[f != MaskValue]
            m, s = slc.mean(), slc.std()
            slc -= m
            slc /= s
            data[:, :, v][f != MaskValue] = slc.astype('float32')
            scale[name] = {'mean': float(m), 'sd': float(s)}

        with open(modelpath+'/'+VAR_FILE_NAME, 'wb') as varfile:
            pickle.dump(scale, varfile)
            varfile.close()

    else:
        f = open(modelpath+'/'+VAR_FILE_NAME, "rb")
        varinfo = pickle.load(f)

        for v, name in enumerate(var_names):
            #print 'Scaling feature %s of %s (%s).' % (v + 1, len(var_names), name)
            f = data[:, :, v]
            slc = f[f != MaskValue]
            m = varinfo[name]['mean']
            s = varinfo[name]['sd']
            slc -= m
            slc /= s
            data[:, :, v][f != MaskValue] = slc.astype('float32')

scale(train, VariablesRNN, True)# scale training sample and save scaling
scale(train,  VariablesRNN, False)# apply scaling to training set
scale(test, VariablesRNN, True)# scale training sample and save scaling
scale(test,  VariablesRNN, False)# apply scaling to training set

'''
lista_vbf=[]
lista_ggf=[]
for i, j in zip(train, y_train):
    if(j==1): lista_vbf.append(i[0][1])
    else: lista_ggf.append(i[0][1])

plt.hist(lista_vbf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram vbf")
plt.show()

plt.hist(lista_ggf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram ggf")
plt.show()
'''
model = run_Training(train, y_train)
'''
test_signal = test
test_background = test
i1=-1
i2=-1
for x_test, y in zip(test, y_test):
    if(y==0):
        test_signal = np.delete(test_signal, i1, 0)
        i2+=1
    else:
        test_background = np.delete(test_background, i2, 0)
        i1 += 1

print(test.shape)
print(test_signal.shape)
print(test_background.shape)
'''

lista_vbf=[]
lista_ggf=[]
for i, j in zip(train, y_train):
    if(j==1): lista_vbf.append(i)
    else: lista_ggf.append(i)

train_signal = np.zeros((len(lista_vbf), nTimeStepsRNN, nVariablesRNN))
for i in range(0, len(lista_vbf)):
    for j in range(0, nTimeStepsRNN):
        for m in range(0, nVariablesRNN):
            train_signal[i, j, m] = lista_vbf[i][j,m]
train_background = np.zeros((len(lista_ggf), nTimeStepsRNN, nVariablesRNN))
for i in range(0, len(lista_ggf)):
    for j in range(0, nTimeStepsRNN):
        for m in range(0, nVariablesRNN):
            train_background[i, j, m] = lista_ggf[i][j,m]



lista_vbf=[]
lista_ggf=[]
for i, j in zip(test, y_test):
    if(j==1): lista_vbf.append(i)
    else: lista_ggf.append(i)

test_signal = np.zeros((len(lista_vbf), nTimeStepsRNN, nVariablesRNN))
for i in range(0, len(lista_vbf)):
    for j in range(0, nTimeStepsRNN):
        for m in range(0, nVariablesRNN):
            test_signal[i, j, m] = lista_vbf[i][j,m]
test_background = np.zeros((len(lista_ggf), nTimeStepsRNN, nVariablesRNN))
for i in range(0, len(lista_ggf)):
    for j in range(0, nTimeStepsRNN):
        for m in range(0, nVariablesRNN):
            test_background[i, j, m] = lista_ggf[i][j,m]


'''
lista_vbf=[]
lista_ggf=[]
for i, j in zip(test_signal, y_train):
    lista_vbf.append(i[0][1])
for i, j in zip(test_background, y_train):
    lista_ggf.append(i[0][1])

plt.hist(lista_vbf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram vbf")
plt.show()

plt.hist(lista_ggf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram ggf")
plt.show()
'''
Batch_size=2048
print('Running model prediction on Xtrain_signal')
yhat_train_signal = model.predict(train_signal, batch_size=Batch_size)
print('Running model prediction on Xtrain_background')
yhat_train_background = model.predict(train_background, batch_size=Batch_size)
print('Running model prediction on Xtest_signal')
yhat_test_signal = model.predict(test_signal, batch_size=Batch_size)
print('Running model prediction on Xtest_background')
yhat_test_background = model.predict(test_background, batch_size=Batch_size)


#plt.scatter(yhat_test_signal, yhat_test_signal, color='red', marker='o', label='Test signal')
#plt.xlabel('Non so')
#plt.ylabel('Score')
#plt.legend(loc='upper left')
'''
lista_vbf=[]
for i in test_signal:
    for j in i:
        if(j[1]>0): lista_vbf.append(j[1])
lista_ggf=[]
for i in test_background:
    for j in i:
        if(j[1]>0): lista_ggf.append(j[1])


plt.hist(lista_vbf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram vbf")
plt.show()

plt.hist(lista_ggf, bins='auto')  # arguments are passed to np.histogram
plt.title("Histogram ggf")
plt.show()
'''
train_signal=[]
for i in yhat_train_signal:
    train_signal.append(i[0])
train_background=[]
for i in yhat_train_background:
    train_background.append(i[0])
test_signal=[]
for i in yhat_test_signal:
    test_signal.append(i[0])
test_background=[]
for i in yhat_test_background:
    test_background.append(i[0])

bins = []
for i in range(1,100):
    bins.append(i/100)
plt.hist(train_signal, bins=bins, alpha=0.5, label='train_signal')
plt.hist(train_background, bins=bins, alpha=0.5, label='train_background')
plt.hist(test_signal, bins=bins, alpha=0.5, label='test_signal')
plt.hist(test_background, bins=bins, alpha=0.5, label='test_background')
plt.ylabel = "jkfjdkfgd"
plt.title("Histogram")
plt.legend(loc='upper right')
plt.show()
plt.savefig('images/Score.png', dpi=300)
