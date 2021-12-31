import os
import pickle
import matplotlib.pyplot as plt
import keras
import gc

from sklearn import metrics

import pandas as pd
import sklearn as sklearn
import numpy as np
import json

import uproot
from pip._vendor.colorama import Back, Fore

import Train
### Read .root files ###
from sklearn.preprocessing import scale

def CreateDataset(perc_of_inputs = 100, listFiles = ['FlatTree_VBFH1000_spin0.root', 'FlatTree_ggFH1000_spin0.root']):
    path = 'FlatTree'
    listFiles = listFiles
    rootBranchSubSample = ['Jet1_pt', 'Jet1_eta', 'Jet1_phi', 'Jet1_E',
            'Jet2_pt', 'Jet2_eta', 'Jet2_phi', 'Jet2_E',
            'Jet3_pt', 'Jet3_eta', 'Jet3_phi', 'Jet3_E',
            'Jet4_pt', 'Jet4_eta', 'Jet4_phi', 'Jet4_E',
           'Jet5_pt', 'Jet5_eta', 'Jet5_phi', 'Jet5_E',
            'Jet6_pt', 'Jet6_eta', 'Jet6_phi', 'Jet6_E']

    DF = pd.DataFrame()
    i=0
    print('Creating datasets')
    for fileInDir in listFiles:
        flatNtuple = path + '/' + fileInDir
        if os.path.isfile(flatNtuple):
            i+=1
            theFile = uproot.open(flatNtuple)
            theTree = theFile.keys()
            tree = uproot.open(flatNtuple)[theTree[0]]
            DF = tree.pandas.df(rootBranchSubSample)
            DF = DF[DF['Jet1_pt']>1]
            if(i==1):
                DF['type'] = 1
            else:
                DF['type'] = 0
            N_events = DF.shape[0]
            if(i==1):
                VBF=DF
            else:
                ggF=DF

    print(Fore.BLUE + 'VBF events = ' + str(VBF.shape[0]) + '  ' + 'ggF events = ' + str(ggF.shape[0]))
    DF=VBF.append(ggF)
    print('  Shuffling datasets')
    DF = sklearn.utils.shuffle(DF,random_state=123) #'123' is the random seed

    VariablesRNN = ['pt', 'eta', 'phi', 'E']

    y = DF['type']
    lista=[]
    for i in y:
        lista.append(i)

    y=lista
    y_train = []
    y_test = []
    DF = DF[rootBranchSubSample]

    N_events = (int)(DF.shape[0] * perc_of_inputs/100)
    train = DF[:(int)(N_events * 0.7)]
    y_train = y[:(int)(N_events * 0.7)]
    test = DF[(int)(N_events * 0.7):N_events]
    y_test = y[(int)(N_events * 0.7):N_events]

    MaskValue = -99.
    nVariablesRNN = 4
    nTimeStepsRNN = 6

    new_train = np.zeros((train.shape[0], nTimeStepsRNN, nVariablesRNN))
    new_test = np.zeros((test.shape[0], nTimeStepsRNN, nVariablesRNN))


    print('  Creating numpy-arrays')
    for i in range(0, train.shape[0]):
        for j in range(0, train.shape[1]):
            new_train[i, int(j/nVariablesRNN), j%nVariablesRNN] = train.iloc[i, j]
    train = new_train

    for i in range(0, test.shape[0]):
        for j in range(0, test.shape[1]):
           new_test[i, int(j/nVariablesRNN), j%nVariablesRNN] = test.iloc[i, j]
    test = new_test

    def scale(data, var_names, savevars, VAR_FILE_NAME='scaling'):
        modelpath = path

        scale = {}
        if savevars:
            for v, name in enumerate(var_names):
                print('  Scaling feature %s of %s (%s).' % (v + 1, len(var_names), name))
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

    print('Scaling..')
    scale(train, VariablesRNN, True)# scale training sample and save scaling
    scale(train,  VariablesRNN, False)# apply scaling to training set
    scale(test, VariablesRNN, True)# scale training sample and save scaling
    scale(test,  VariablesRNN, False)# apply scaling to training set
    return train, y_train, test, y_test

def Divide_datasets(train, y_train, test, y_test):

    print('Dividing datasets')
    nVariablesRNN = 4
    nTimeStepsRNN = 6
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
    print('')
    print(Fore.BLUE + 'Train events = ' + str(train.shape[0]) + '  ' + 'Test events = ' + str(test.shape[0]))
    print(Fore.BLUE + 'Train Signal ev = ' + str(train_signal.shape[0]) + '  ' + 'Train Background ev = ' + str(train_background.shape[0]))
    print(Fore.BLUE + 'Test Signal ev = ' + str(test_signal.shape[0]) + '  ' + 'Test Background ev = ' + str(test_background.shape[0]))
    print(Fore.WHITE)
    return train_signal, train_background, test_signal, test_background


def run_TrainandTest(
                     train, y_train, test, y_test,
                     train_signal, train_background, test_signal, test_background,
                     string_save='', epochs=100, lr=0.001, B_size=2048,
                     DimRetSeqLayers=25, DimNORetSeqLayers=25, dropout1=0.3, dropout2=0.3, Params=1, activation='sigmoid', verbose=False
                     ):
    model, history = Train.run_Training(train, y_train, epochs=epochs, lr=lr, B_size=B_size,
                               DimRetSeqLayers=DimRetSeqLayers, DimNORetSeqLayers=DimNORetSeqLayers,
                               dropout1=dropout1, dropout2=dropout2, Params=Params, activation=activation,
                               verbose=verbose
                               )



    Batch_size=16
    yhat_train_signal = model.predict(train_signal, batch_size=Batch_size)
    yhat_train_background = model.predict(train_background, batch_size=Batch_size)
    yhat_test_signal = model.predict(test_signal, batch_size=Batch_size)
    yhat_test_background = model.predict(test_background, batch_size=Batch_size)

    score = model.evaluate(test, y_test, batch_size=Batch_size, verbose=False)
    acc = score[1]
    print(Fore.BLUE + "--------------------------")
    print(Back.BLUE + "       TESTING RNN        ")
    print(Fore.BLUE + "--------------------------")
    print('Accuracy = ' + str(acc))


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

    bins1 = []
    for i in range(1,25):
        bins1.append(i/25)
    bins2 = []
    for i in range(1,100):
        bins2.append(i/100)

    yt = []
    test = []
    for i in range(0, len(train_signal)):
        yt.append(1)
        test.append(train_signal[i])
    for i in range(0, len(train_background)):
        yt.append(0)
        test.append(train_background[i])

    fpr, tpr, thresholds = metrics.roc_curve(yt, test, pos_label=1)
    lista=[]
    for i in range(35): lista.append((int)(len(fpr)/36)*i)
    print('Array di ggF efficiency')
    for i in lista:
        print(str(fpr[i]))
    print('Array di VBF efficiency')
    for i in lista:
        print(str(tpr[i]))
    lista=[]
    for i in range((int)(len(thresholds)/1000)):
        passa = True
        #for num in lista:
            #if((int)(thresholds[num]*100) == (int)(thresholds[i])): passa=False
        #if(passa): lista.append(i)
    print('Array di thresholds:')
    for i in lista:
        print(str(thresholds[i]))
    print('Array di ggF efficiency')
    for i in lista:
        print(str(fpr[i]))
    print('Array di VBF efficiency')
    for i in lista:
        print(str(tpr[i]))

    lista_est=[]
    for i in range(len(fpr)):
        lista_est.append(tpr[i]*(1-fpr[i]))
    massimo=0
    indice=-1
    for i in range(len(lista_est)):
        if(lista_est[i]>massimo):
            massimo = lista_est[i]
            indice=i
    print('')
    print('MIGLIORE ESTIMAZIONE!')
    print(massimo)
    print(str(tpr[indice]*100)+'_____'+str(fpr[indice]*100))


    plt.scatter(tpr, fpr, color='black', marker='.', label='Test ROC')
    plt.title("ROC curve for Signal vs Background")
    plt.xlabel('True Positive')
    plt.ylabel('False Positive')
    if(string_save!='None'): plt.savefig('images/ROC'+string_save+'.png', dpi=300)
    plt.close()

    plt.hist(train_signal, bins=bins1, alpha=0.5, label='train_signal', normed=1)
    plt.hist(train_background, bins=bins1, alpha=0.5, label='train_background', normed=1)
    plt.hist(test_signal, bins=bins1, alpha=0.9, label='test_signal', normed=1)
    plt.hist(test_background, bins=bins1, alpha=0.9, label='test_background', normed=1)
    plt.xlabel('RNN Score')
    plt.ylabel('Normalized Events')
    plt.title("Score Histogram")
    plt.legend(loc='upper right')
    if(string_save!='None'): plt.savefig('images/Score'+string_save+'_bin25.png', dpi=300)
    plt.close()

    plt.hist(train_signal, bins=bins2, alpha=0.5, label='train_signal', normed=1)
    plt.hist(train_background, bins=bins2, alpha=0.5, label='train_background', normed=1)
    plt.hist(test_signal, bins=bins2, alpha=0.9, label='test_signal', normed=1)
    plt.hist(test_background, bins=bins2, alpha=0.9, label='test_background', normed=1)
    plt.xlabel('RNN Score')
    plt.ylabel('Normalized Events')
    plt.title("Score Histogram")
    plt.legend(loc='upper right')
    if(string_save!='None'): plt.savefig('images/Score'+string_save+'_bin100.png', dpi=300)
    plt.close()

    plt.plot(history.history['loss'])
    plt.plot(history.history['val_loss'])
    plt.title('Model loss')
    plt.ylabel('Loss')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Val'], loc='upper right')
    if(string_save!='None'): plt.savefig('images/Loss'+string_save+'.png', dpi=300)
    plt.close()

    keras.backend.clear_session()
    del model
    gc.collect()
    return acc