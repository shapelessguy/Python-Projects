from keras.callbacks import ModelCheckpoint, EarlyStopping

from keras.optimizers import Adam
from pip._vendor.colorama import Fore, Back
import RNN


path = 'FlatTree'

def run_Training(X_train, y_train, epochs=200, lr = 0.001, B_size=4096,
                 DimRetSeqLayers = 25, DimNORetSeqLayers = 25, dropout1 = 0.3, dropout2 = 0.3, Params = 1, activation='sigmoid',
                 verbose=False
                 ):
    model = RNN.BuildTestRNN(X_train, DimRetSeqLayers = DimRetSeqLayers, DimNORetSeqLayers=DimNORetSeqLayers,
                             dropout1 = dropout1, dropout2 = dropout2, Params = Params, activation=activation)
    model.compile(optimizer=Adam(lr=lr), metrics=['accuracy'], loss='binary_crossentropy')

    print(Fore.BLUE + "--------------------------")
    print(Back.BLUE + "       TRAINING RNN       ")
    print(Fore.BLUE + "--------------------------")
    try:
        modelMetricsHistory = model.fit([X_train], y_train, batch_size=B_size,
                                        verbose=verbose,
                                        callbacks=[
                                        EarlyStopping(verbose=verbose, patience=10, monitor='val_loss'),

                                        ModelCheckpoint(path + '/model.h5', monitor='val_loss', verbose=verbose,
                                                        save_best_only=True)

                                        ],
                                        epochs=epochs,
                                        validation_split=0.2)
    except NameError:
        print('bo')
    return model, modelMetricsHistory