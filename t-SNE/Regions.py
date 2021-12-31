import numpy as np
from sklearn import svm
from sklearn.neighbors import KNeighborsClassifier as knn
from sklearn.model_selection import GridSearchCV

class clusters:
    svm_score = 0.
    knn_score = 0.
    svm_clf = None
    knn_clf = None

    def __init__(self, X, y, train_test_ratio=0.8):
        self.X_test = X[int(len(X)*train_test_ratio):, :]
        self.y_test = y[int(len(X)*train_test_ratio):]
        self.X_train = X[:int(len(X)*train_test_ratio), :]
        self.y_train = y[:int(len(X)*train_test_ratio)]

    def trainSVM(self, kernel='linear', C=1, gamma=1, opt=False):
        optim = ''
        if opt:
            optim += ' with optimizer on (gridSearch)'
        print('\nTraining with SVM' + optim)
        parameters = {'kernel': ('linear', 'rbf'), 'C': [2**i for i in range(-3, 4)],
                      'gamma': [10**i for i in range(-5, 0)]}
        if opt:
            self.svm_clf = GridSearchCV(svm.SVC(), parameters)
            self.svm_clf.fit(self.X_train, self.y_train)
            best = self.svm_clf.best_index_
            C = self.svm_clf.cv_results_['param_C'][best]
            gamma = self.svm_clf.cv_results_['param_gamma'][best]
            kernel = self.svm_clf.cv_results_['param_kernel'][best]
        else:
            self.svm_clf = svm.SVC(kernel=kernel, C=C, gamma=gamma).fit(self.X_train, self.y_train)
        self.svm_score = self.svm_clf.score(self.X_test, self.y_test)
        print(f'SVM score: {self.svm_score} \nParams:  kernel={kernel}  C={C}  gamma={gamma}')


    def trainKNN(self, k=10):
        print('\nTraining with KNN')
        self.knn_clf = knn(k).fit(self.X_train, self.y_train)
        self.knn_score = self.knn_clf.score(self.X_test, self.y_test)
        print(f'KNN (k={k}) score: {self.knn_score}')


    def predict(self, X, clf='svm'):

        #Check on parameter clf
        if clf == 'svm':
            if self.svm_clf is None:
                if self.knn_clf is not None:
                    clf = 'knn'
                else:
                    return None

        #Predict with KNN algorithm
        if clf == 'knn':
            if len(X.shape) < 2:
                X = X[np.newaxis, :]
            result = self.knn_clf.predict(X)
            if X.shape[0] == 1:
                return result[0]
            return result

        #Predict with SVM algorithm
        elif clf == 'svm':
            if len(X.shape) < 2:
                X = X[np.newaxis, :]
            result = self.svm_clf.predict(X)
            if X.shape[0] == 1:
                return result[0]
            return result

        return None


    def pred_acc(self, predictedY, trueClasses, clf='svm'):
        return np.sum(np.equal(self.predict(predictedY, clf), trueClasses)) / len(predictedY)

