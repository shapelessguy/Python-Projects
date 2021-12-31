import Functionals as F
import Visualization as V
import Regions as R
import pandas as pd
import numpy as np
import random
from matplotlib import pyplot as plt
from sklearn.datasets import load_digits


class data:
    def __init__(self, X=None, target=None, Y=None, train_test_ratio=1.):
        """
        It handles the data throughout the entire processing of them.
        The main purposes are those to hold separated but ordered the subset
        of the raw data X, the target data (corresponding to the class values)
        and the reduced data Y.

        :param train_test_ratio: proportion between train and test
        :param X: raw data
        :param target: array of class labels
        :param Y: reduced data of X
        """
        self.X = X
        self.target = target
        self.Y = Y
        self.Y_train = None
        self.Y_test = None
        self.train_test_ratio = train_test_ratio

        if X is not None:
            self.split(train_test_ratio)

    def split(self, train_test_ratio=1.):
        """
        It splits the data between a train and a test subset.

        :param train_test_ratio: proportion between train and test
        """
        indexes = [i for i in range(len(self.X))]
        random.shuffle(indexes)

        indexes = np.array(indexes)
        f = indexes[:int(len(self.X)*train_test_ratio)]
        l = indexes[int(len(self.X)*train_test_ratio):]
        self.X_train = self.X[f, :]
        self.target_train = self.target[f]
        self.X_test = []
        self.target_test = []
        if len(l) > 0:
            self.X_test = self.X[l, :]
            self.target_test = self.target[l]
        if self.Y is not None:
            self.Y_train = self.Y[f, :]
            if len(l) > 0:
                self.Y_test = self.Y[l, :]

    def save(self, name):
        """
        It saves the data to a local path (the t-SNE results).

        :param name: identification of the path name pointing to the file
        """
        df_train = self.makeDF(self.X_train, self.target_train, self.Y_train)
        df_train.to_csv(f'{name}_train_{self.train_test_ratio}.csv', sep=';', index=False)
        df_test = self.makeDF(self.X_test, self.target_test, self.Y_test)
        df_test.to_csv(f'{name}_test_{self.train_test_ratio}.csv', sep=';', index=False)

    def loadFrom(self, name=None):
        """
        It loads the data from a local path (the t-SNE results), otherwise will
        fill itself autonomously with data from the official mnist dataset.
        It takes the data, target and y values necessary
        to create the dataset to use for other methods.

        :param name: identification of the path name pointing to the file
        :return: data istance
        """
        fullname = f'{name}_{self.train_test_ratio}.csv'
        try:
            df_train = pd.read_csv(f'{name}_train_{self.train_test_ratio}.csv', sep=';')
            df_test = pd.read_csv(f'{name}_test_{self.train_test_ratio}.csv', sep=';')
        except:
            print(f'Files {name}_train(test)_{self.train_test_ratio}.csv not found')
            name = None

        if name is None:
            sk_df = load_digits()
            data_ = data(sk_df.data, sk_df.target, train_test_ratio=self.train_test_ratio)
            return data_

        targ_index = 0
        for i in range(len(df_train.columns)):
            if df_train.columns[i][0] != 'X':
                targ_index = i
                break

        self.X_train = df_train.values[:, :targ_index]
        self.target_train = df_train.values[:, targ_index]
        if targ_index != len(df_train.columns):
            self.Y_train = df_train.values[:, targ_index + 1:]

        self.X_test = df_test.values[:, :targ_index]
        self.target_test = df_test.values[:, targ_index]
        if targ_index != len(df_test.columns):
            self.Y_test = df_test.values[:, targ_index + 1:]

        print(f'\nDataset {fullname} info:\nTrain X shape: {self.X_train.shape}\n'
              + f'Train target shape: {self.X_train.shape}\nTrain Y shape: {self.Y_train.shape}\n'
              + f'Test X shape: {self.X_test.shape}\nTest target shape: {self.target_test.shape}\n'
              + f'Test Y shape: {self.Y_test.shape}')
        return self


    def makeDF(self, data, target, Y):
        """
        Creates and saves a dataset given the data, target data and the results of the method used in advance (t-SNE).

        :param data: input data
        :param target: target variable
        :param Y: results method used (t-SNE)
        :return: corrisponding pandas dataframe
        """

        df = {f'X{i}': data[:, i] for i in range(data.shape[1])}
        df['target'] = target
        if Y is not None:
            for i in range(Y.shape[1]):
                df['Y' + str(i)] = Y[:, i]
        df = pd.DataFrame(df)
        return df



def runTSNE(iter_, data1, no_dims1=2, compSigma=False,
            force=False, data2=None, no_dims2=2, animation=True, save=False):
    """
    Runs an istance of tSNE over 1 (or 2) dataset. Eventually, new csv files will be created
    in order to save time for future re-applications of this method over the same datasets.
    In the end, a new animation 2D and 3D can be created to visualize the behavior of the data
    points throughout the discrimination process inducted by the algorithm.

    :param data1: first input data
    :param no_dims1: dimensions of the reduced space on the first input data
    :param data2: second input data (optional)
    :param no_dims2: dimensions of the reduced space on the second input data
    :param animation: if True, an animation of tSNE process is saved in a local mp4 file
    :param save: if True, data obtained through the tSNE will be stored for future runs
    """
    p_saved = True
    if data1.Y_test is None or data2.Y_test is None or force:
        p_saved = False
    X_pca1 = F.PCAMethod(data1.X_train)
    target1 = data1.target_train
    tsne1 = F.TSNE(X_pca1.X, no_dims=no_dims1, perplexity=30.0)
    if data1.Y_test is None or force:
        tsne1.run(iterations=iter_)
        data1.Y_train = tsne1.Y
    else:
        if compSigma:
            tsne1.computeP()

    target2 = []
    tsne2 = None
    if data2 is not None:
        X_pca2 = F.PCAMethod(data2.X_train)
        tsne2 = F.TSNE(X_pca2.X, no_dims=no_dims2, perplexity=30.0)
        target2 = data2.target_train
        if data2.Y_test is None or force:
            tsne2.run(iterations=iter_)
            data2.Y_train = tsne2.Y
        else:
            if compSigma:
                tsne2.computeP()

    if save:
        data1.save('data1')
        if tsne2 is not None:
            data2.save('data2')

    if animation and not p_saved:
        V.animation(tsne=tsne1, target=target1, var=True, title=f't-SNE {no_dims1}D   n={len(target1)}',
                    tsne2=tsne2, target2=target2, var2=True, title2=f't-SNE {no_dims2}D   n={len(target2)}',
                    save='Gifs//wow.mp4')
        plt.clf()
        plt.close('all')


def runANN(data):
    data.Y_test = data.Y_train[:len(data.X_test), :data.Y_train.shape[1]]
    return


def main():
    # Hello there
    # Hi bitcheees


    # Load the data
    data1 = data(train_test_ratio=0.8).loadFrom('data1')
    data2 = data(train_test_ratio=0.8).loadFrom('data2')

    # Apply the t-SNE method
    runTSNE(iter_=400, force=False, data1=data1, no_dims1=2,
            data2=data2, no_dims2=3, animation=False, save=True)


    # Retrieve the map of classes within the low dimensional space
    cluster = R.clusters(data1.Y_train, data1.target_train)
    cluster.trainSVM(kernel='rbf', C=2, gamma=0.1, opt=False)

    # Plot the map if 2 dimensional
    V.plotMap2D(data1, type='train', cluster=cluster)

    # Apply a ANN to approximate the previous mapping procedure
    runANN(data1)

    # Evaluate the accuracy of the neural network
    acc = cluster.pred_acc(predictedY=data1.Y_test, trueClasses=data1.target_test)
    print(f'\nAccuracy of the ANN: {acc}')

    # Plot the map together with the test samples if 2 dimensional
    V.plotMap2D(data1, type='test', cluster=cluster)


if __name__ == "__main__":
    main()

