import numpy as np

class indexedNpArray:
    def __init__(self, array):
        self.matrix = array
        if array.shape[1] > 1:
            self.indexes = [i+1 for i in range(array.shape[1])]
        else:
            self.indexes = [i+1 for i in range(array.shape[0])]

    def take(self, listIndexes):
        new_listIndexes = [i-1 for i in listIndexes]
        if self.matrix.shape[1] > 1:
            return self.matrix[:, new_listIndexes].copy()
        else:
            return self.matrix[new_listIndexes, :].copy()

    def print(self):
        if self.matrix.shape[1]>1:
            print('Indexed matrix')
            indexedArray = np.append(np.array(self.indexes).reshape((1, len(self.indexes))), self.matrix, axis=0)
        else:
            print('Indexed vector')
            indexedArray = np.append(np.array(self.indexes).reshape((len(self.indexes), 1)), self.matrix, axis=1)
        print(indexedArray)

