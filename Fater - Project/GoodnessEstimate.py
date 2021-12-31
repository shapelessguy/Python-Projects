import numpy as np
from scipy.optimize import minimize


def correctRange(y):
    # Returns the correct range for the given array, starting with its maximum
    maximum = max(y)
    index = y.index(maximum)
    if index < 3 * len(y) / 4:
        return y[index:]
    else:
        return y


def hyperbolePredictions(k, q, x):
    # Returns an array of hyperbole evaluations over different x
    y = [(k / ix + q) for ix in x]
    return np.array(y)


def goodness(yPred, yTrue):
    # Returns the MSE for the prediction
    return ((yPred - yTrue) ** 2).sum()


def lossFunction(y):
    # Returns the loss function when trying to interpolate a given array as an hyperbole
    def function(parameters):
        k, q = parameters
        x = range(1, len(y) + 1)
        error = goodness(hyperbolePredictions(k, q, x), y)
        return error

    return function


def optimization(y):
    # Returns the parameters that best fit a given array into an hyperbole
    parameters = minimize(lossFunction(y), (1, 0))
    return parameters['x']


def prediction(y):
    # Given an array y, it returns a tuple like this (minimumPosition, minimum, limit) where minimum and minimumPosition
    # are what their name suggest and limit is the limit for x that goes to infinity of its hyperbolic interpolation
    # or -1 if the limit goes to infinity
    if len(y) > 6: minimum = min(y[6:])
    else: minimum = min(y)
    index = y.index(minimum)

    y = correctRange(y)
    parameters = optimization(y)

    x = range(1, len(y) + 1)
    fitError = goodness(hyperbolePredictions(parameters[0], parameters[1], x), y)
    #print(fitError)

    if fitError:
        return index, minimum, parameters[1]
    else:
        return index, minimum, -1
