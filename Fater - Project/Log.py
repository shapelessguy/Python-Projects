import Functions as fun
import statistics
from matplotlib import pyplot as plt

class log:
    def __init__(self, input):

        if type(input) == tuple:
            self.score = input[0]
            self.epochs = input[1]
            self.interval_eval = input[2]
            self.target = input[3]
            self.loss_validation_estimate = input[4]
            self.parameters = input[5]
        elif input is None:
            self.score = (100, 0)
            self.epochs = 0
            self.interval_eval = 0
            self.target = ''
            self.loss_validation_estimate = (0,)
            self.parameters = (0,)
        elif type(input) == str:
            fields = input.split('#')
            self.score = [float(el) for el in tuple(fields[0].split('|'))]
            self.epochs = int(fields[1])
            self.interval_eval = int(fields[2])
            self.target = fields[3]
            self.loss_validation_estimate = [float(el) for el in tuple(fields[4].split('|'))]
            self.parameters = tuple(float(el) for el in tuple(fields[5].split('|')))
        self.goodness = self.score[0]

    def serialize(self):
        output = ''
        output += '|'.join(str(x) for x in self.score) + '#'
        output += str(self.epochs) + '#'
        output += str(self.interval_eval) + '#'
        output += self.target + '#'
        output += '|'.join(str(x) for x in self.loss_validation_estimate) + '#'
        output += '|'.join(str(x) for x in self.parameters)
        return output

    def verbose(self):
        loss = []
        loss.append(self.loss_validation_estimate[0])
        loss.append(self.loss_validation_estimate[int(len(self.loss_validation_estimate)/2)])
        loss.append(self.loss_validation_estimate[-1])
        output = 'Score: ('
        output += ', '.join(['{:.3f}'.format(float(num)) for num in self.score]) + ') Target: {} Loss validation: ('.format(self.target)
        aggregation = self.parameters[0]
        if type(aggregation) != str: aggregation = fun.conversion(aggregation)
        output += ', '.join(['{:.3f}'.format(float(num)) for num in loss]) + ") Param: ('{}', ".format(aggregation)
        output += ', '.join(['{:.3f}'.format(float(num)) for num in self.parameters[1:]]) + ')'
        return output

    def print(self):
        print(self.verbose())

def readLogs_fromFile(fileName, n_logs=0, aggregation='', target='', dropout=[0,1]):
    logs = []
    try:
        with open(fileName, 'r') as file:
            for line in file.readlines():
                log_ = log(line)
                if aggregation != '':
                    if fun.conversion(log_.parameters[0]) != aggregation: continue
                if target != '':
                    if log_.target != target: continue
                if log_.parameters[6] < dropout[0] or log_.parameters[6] > dropout[1]: continue
                logs.append(log_)
        if n_logs > len(logs) or n_logs == 0:
            return logs, len(logs)
        else:
            return logs[(len(logs)-n_logs):], len(logs)
    except Exception as ex:
        print('Exception',ex)
        return [], 0

def convergence(log_bag, clusterSize:int=1):
    if len(log_bag) == 0: return
    logs = [el.goodness for el in log_bag]
    log_target = list(set([el.target for el in log_bag]))
    clusters = []
    index = len(logs)
    while index >= clusterSize:
        clusters.append(logs[index-clusterSize:index])
        index -= clusterSize
    mean = [sum(element) / clusterSize for element in clusters]
    mean.reverse()
    devst = [statistics.stdev(element) if len(element) > 1 else 0 for element in clusters]
    plt.scatter(range(len(mean)), mean, label='mean MSE')
    plt.errorbar(range(len(mean)), mean, yerr=devst, label='dev standard')
    target = ''
    if len(log_target) == 1: target = ' - target: ' + log_target[0]
    plt.title('Evolutive algorithm convergence{}'.format(target))
    plt.xlabel('Generations')
    plt.ylabel('mean of MSE')
    plt.legend(loc='lower left')
    plt.show()
    plt.clf()

def describe(logs, top=1):
    if top > len(logs): top = len(logs)
    top_log = []
    top_idx = -1
    top_goodness = 10000
    for i in range(top):
        for index in range(len(logs)):
            if logs[index].loss_validation_estimate[1] != 0 and (logs[index].loss_validation_estimate[2]-logs[index].
                    loss_validation_estimate[1])/logs[index].loss_validation_estimate[1] > 0.05: continue
            if logs[index].goodness < top_goodness:
                top_idx = index
                top_goodness = logs[index].goodness
        top_log.append(logs.pop(top_idx))
        top_idx = -1
        top_goodness = 10000
    for log in top_log:
        log.print()
    return top_log
