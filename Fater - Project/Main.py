import Evolutive as EV
import Analysis as AN
import Functions as fun
import statistics
from matplotlib import pyplot as plt
import Log
import pandas as pd

bestHyperParam = {
    # complete run on evolutionary algorithm
    'Product 3':(1.0, 0.0, 0.13, 5.0, 1.0, 0.0, 0.3802290077717957, 4.0, 7.0, 5.0, 44.0, 0.89),

    # same parameters of product 3
    'Product 2':(1.0, 0.0, 0.13, 5.0, 1.0, 0.0, 0.3802290077717957, 4.0, 7.0, 5.0, 44.0, 0.89),

    # partial runs on evolutionary algorithm based on the product 3 hyperparameters
    'Product 4':(1.0, 0.0, 0.1, 7.0, 1.0, 0.0, 0.195, 25.0, 7.0, 6.0, 45.0, 0.91),
    'Product 5':(1.0, 0.0, 0.04, 5.0, 1.0, 0.0, 0.18, 24.0, 6.0, 7.0, 46.0, 0.9),
    'Product 6':(1.0, 0.0, 0.15, 5.0, 1.0, 0.0, 0.22, 25.0, 6.0, 7.0, 49.0, 0.87),
    'Product 7':(1.0, 0.0, 0.08, 6.0, 1.0, 1.0, 0.185, 25.0, 8.0, 8.0, 44.0, 0.89),
    'Product 8':(1.0, 0.0, 0.08, 5.0, 1.0, 0.0, 0.21, 20.0, 5.0, 8.0, 47.0, 0.9),
    'Product 9':(1.0, 0.0, 0.07, 7.0, 1.0, 0.0, 0.225, 24.0, 6.0, 6.0, 45.0, 0.9),
    'Product 10':(1.0, 0.0, 0.06, 7.0, 1.0, 0.0, 0.011173569112543219, 22.0, 6.0, 5.0, 44.0, 0.93)
}

def runGRU():
    '''
    Trains and tests data on a certaint architecture (look at Analysis)
    Parameters:
        - hyperparameters, tuple:
            {
                aggregation, float or str: aggregation factor that specify the aggregation level of dataset samples. The
                                           aggregations can vary from a 1D (1 day) to 7D (7 days), that can be mapped
                                           into a float interval [0,1], in which 1D will correspond to 0 and 7D to 1.
                pastHistory, float: proportion of the history sequence compared to the prediction sequence lenght. If
                                 this value is equal to 0, then the history size will be equal to the prediction size,
                                 while if equals to 1, the history size will be equal to the prediction one times 2 ...
                                (works only for the first method, always zero for the second one).
                testProp, float: proportion of the test set compared to the maximum one that can be used given the
                                 implicit constraints. If this value is equal to 0, then the test size will count only
                                 the last sample of the original dataset, and the resulting mse will be given by the
                                 computation on this very last sequence.
                epochs, integer: number of epochs used for the train phase of the RNN, if zero the RNN will use an Early
                                 Stop mechanism. Note that higher values of epochs will correspond to much less smoothed
                                 predicted curves.
                kernelSize, integer: size of the window used for the convolutional layer in the middle. If 1 the
                                     architecture will not add this layer.
                dilations, integer: number of dilation that will define the amplitude of the waveNet. If 0 the
                                    architecture will not add these series of (convolutional) layers.
                dropout, float: number within the interval [0,1[ specify the dropout factor within and between the GRU
                                layers.
                conv1, integer: number of filters within the waveNet
                conv2, integer: number of filters within the core convolutional layer
                n1, integer: number of neurons that compose the GRU core layer
                n2, integer: number of neurons that compose the additional GRU layer. If 0 the
                             architecture will not add this layer.
                activation, float or str: activation function of the final neuron optionally mapped into the interval
                                          [0,1]. The activation levels are: none, sigmoid, relu, softmax, tanh.
            }
        - target, str: target of the analysis (for example 'Product 3')
        - saveGraph, boolean: save the resultant plot into the folder Plots within the main folder if predict==False,
                                within the folder Predictions otherwise
        - iterative: specify one of the two methodologies adopted in order to forecast
    :return: tuple of goodness and other specific metrics useful for the charateristics of the RNN istance if
                predict==False, list of predicted values otherwise
    '''
    fun.initializeDatasets()
    parameters = (1.0, 0.0, 0.13, 5.0, 1.0, 0.0, 0.3802290077717957, 4.0, 7.0, 5.0, 44.0, 0.89)
    AN.runGRU(hyperparameters=parameters, target='Product 3', saveGraph=True, verbose=1)

def runEV(target):
    '''
    Save into the file log.txt a series of output generated from all instances of RNN by the worst goodness fit out of
    three (to prevent eventual statistical fluctuations of the result given by a single RNN instance). From generation to
    generation this algorithm will try to create an even more powerful population of individuals, each one representing
    a set of hyper-parameters that will express themselves as the goodness of prediction of the RNN that uses these
    hyper-parameters.
    Parameters:
        - pop_size, integer: number of individuals that populate every generation of hyperparameters-sets
        - ngen, integer: number of generations in which individuals will be selected, will mate each others, generating
                         eventually an offspring of more phenotypically powerful individuals.
        - cxpb, float: Crossing over probability.
        - mutpb, float: Mutation probability of each individual.
    :param target: str - target of the analysis (for example 'Product 3')
    :return: None
    '''
    EV.run_EvolutiveAlgorithm(pop_size=60, ngen=1, target=target, cxpb=0.7, mutpb=0.5)

def final(target):
    '''
    Given the best hyper-parameters for a certain target in log.txt file, there will be computed a certain number of
    other iterations for each hyper-parameter set, in order to retrieve a mean and a deviation standard associated to
    the goodness of the RNN architecture determined by the hyper-parameters themselves. The results will be saved into
    the folder Results and will be chosen the set that minimize the mean of MSE. Although, for the analysis, the set
    that could be chosen are the ones that present the minimum variance.
    :param target: str - target of the analysis (for example 'Product 3')
    :return: None
    '''
    top = 10
    iterations = 15
    fun.initializeDatasets()
    all_logs = Log.readLogs_fromFile('logs.txt', aggregation='7D', target=target, dropout=[0, 0.4])[0]
    all_logs = Log.describe(all_logs, top=top)
    results = {}
    for log in all_logs:
        parameters = log.parameters
        scores = [AN.runGRU(parameters=parameters, target=target, saveLog=False, goodness='last', saveGraph=True,
                            iterative=True, verbose=0).goodness for i in range(iterations)]
        mean = sum(scores)/len(scores)
        devst = statistics.stdev(scores)
        results[log.parameters] = (mean, devst)
    mean = []
    devstd = []
    idx = 0
    best_mean = 10000000
    best_key = -1
    for key in results:
        print('Index: {} - Mean and Standard Deviation: {}'.format(idx, results[key]))
        with open("Results/logs.txt", "a+") as file:
            file.write('Target: {} - Index: {} - Param: {} - Mean and Standard Deviation: {}\n'.format(target, idx, key, results[key]))
        mean.append(results[key][0])
        devstd.append(results[key][1])
        if results[key][0] < best_mean:
            best_mean = results[key][0]
            best_key = key
        idx += 1
    try:
        print('Probably best parameters for {}: {}\nMean and Standard Deviation: {}'.format(target, best_key, results[best_key]))
        with open("Results/logs.txt", "a+") as file:
            file.write('Target: {} - Best Param: {} - Mean and Standard Deviation: {}\n'.format(target, best_key, results[best_key]))
    except Exception: None

    fig, axis = plt.subplots(1, figsize=(15, 10))
    axis.scatter(range(len(mean)), mean, label='mean MSE')
    axis.errorbar(range(len(mean)), mean, yerr=devstd, label='dev standard', linewidth=3)
    axis.set_title('Best parameters for {}'.format(target))
    axis.set_xlabel('Parameter index')
    axis.set_ylabel('mean of MSE')
    axis.legend(loc='best')
    fig.savefig('Results/Target_{}.png'.format(target))
    plt.clf()

def getPredictions(targets):
    fun.initializeDatasets()
    output = {'Index':[]}
    for target in targets:
        output[target] = AN.runGRU(hyperparameters=bestHyperParam[target], target=target, saveGraph=True,
                                   iterative=False, verbose=1, predict=True)
    output['Index'] = list(range(len(output[targets[0]])))
    dataframe = pd.DataFrame(output)
    dataframe.to_csv('Predictions\Predictions.csv', index=False)

if __name__ == '__main__':
    targets = ['Product 2', 'Product 3', 'Product 4', 'Product 5', 'Product 6', 'Product 7', 'Product 8', 'Product 9', 'Product 10']
    getPredictions(targets)