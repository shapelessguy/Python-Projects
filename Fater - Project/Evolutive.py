import Analysis as AS
import Functions as fun
import Log
import matplotlib.pyplot as plt
import deap
import random
import numpy as np
from deap import base
from deap import creator
from deap import tools
import math

IND_size = 1
maxLoss = 0
TARGET = ''
ind_ = []

def plot_train_history(history, title):
    loss = history.history['loss']
    val_loss = history.history['val_loss']
    epochs = range(len(loss))
    plt.figure()
    plt.plot(epochs, loss, 'b', label='Training loss')
    plt.plot(epochs, val_loss, 'r', label='Validation loss')
    plt.title(title)
    plt.legend()
    plot_train_history(history, 'Single Step Training and validation loss')
    plt.show()

def evaluate_(individual):
    global evaluated
    evaluated += 1
    print('  ----- Evaluation: {}'.format(evaluated))
    aggregation = 1
    pastHistory_fac = 0
    testProp = individual[0]
    epochs = int(individual[1]*20)
    if epochs < 5: epochs = 0
    kernelSize = int(1 + individual[2]*3)
    dilations = int(0 + individual[3]*6)
    dropout = individual[4]/2
    conv1_filters = int(1 + individual[5]*39)
    conv2_filters = int(1 + individual[6]*39)
    n1 = int(1 + individual[7]*49)
    n2 = int(individual[8]*50)
    activation = individual[9]
    parameters = (aggregation, pastHistory_fac, testProp, epochs, kernelSize, dilations, dropout,
                  conv1_filters, conv2_filters, n1, n2, activation)

    try:
        logs = [AS.runGRU(hyperparameters=parameters, target=TARGET, saveLog=False, goodness='last', iterative=True) for i in range(3)]
        goodnesses = [log.goodness for log in logs]
        max_log = logs[goodnesses.index(max(goodnesses))]
        with open("logs.txt", "a+") as file: file.write(max_log.serialize() + '\n')
        loss = float(max_log.goodness)
        if loss < 0:
            loss = maxLoss
    except Exception as ex:
        print(ex)
        loss = maxLoss
    return loss

def binomialChoice(p):
    return np.random.binomial(100, p) / 100

index = 0
def createRandomParameters():
    global index
    output = random.random()
    #  Biased choices of initial hyperparameters. This is a finishing touch to precisely determine the best
    #  hyperparameters for minimizing mse relative to a specific product (in this case product 3) after a first
    #  phase of uniform research into the hyperparameters space
    #    if index == 0: output = binomialChoice(0.10)       #  testProp
    #    elif index == 1: output = binomialChoice(0.30)     #  epochs
    #    elif index == 2: output = binomialChoice(0.20)     #  kernelSize
    #    elif index == 3: output = binomialChoice(0.10)     #  dilations
    #    elif index == 4: output = binomialChoice(0.40)     #  dropout
    #    elif index == 5: output = binomialChoice(0.60)     #  conv1
    #    elif index == 6: output = binomialChoice(0.15)     #  conv2
    #    elif index == 7: output = binomialChoice(0.15)     #  n1
    #    elif index == 8: output = binomialChoice(0.90)     #  n2
    #    elif index == 9: output = binomialChoice(0.90)     #  activation
    #    else: output = random.random()
    index += 1
    if index == IND_size: index = 0
    return output

evaluated = 0
def evolution(toolbox, pop_size, ngen, target, cxpb, mutpb):
    global evaluated
    print('-------\nGenerating a population of {} individuals  -  {} generations'.format(pop_size, ngen))
    pop = toolbox.population(n=pop_size)
    print('.. Evolutive algorithm started ..\n')

    means = [0]
    fitnesses = []
    continue_fitnesses = []
    logs, n_logs = Log.readLogs_fromFile('logs.txt', len(pop), aggregation='7D', target=target)
    all_logs = Log.readLogs_fromFile('logs.txt', aggregation='7D', target=target)[0]
    if len(all_logs) >= pop_size: Log.convergence(all_logs, pop_size)

    for index in range(len(logs)):
        for sub_index in range(len(pop[index])):
            pop[index][sub_index] = logs[index].parameters[sub_index]
        fitnesses.append(logs[index].score[0])
    if len(logs) < len(pop):
        print('---------------------------------------')
        print('            GENERATION {}'.format(0))
        print('---------------------------------------')
        evaluated = len(logs)
        continue_fitnesses = list(map(toolbox.evaluate, pop[len(logs):]))
    fitnesses = fitnesses + continue_fitnesses
    means.append(sum(fitnesses) / len(fitnesses))

    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = (fit,)
    for g in range((n_logs - len(logs))//pop_size, ngen):
        evaluated = 0
        inc = '-'
        if means[-1]>means[-2]: inc = '+'
        inc = '  incr: {}{:3f}  '.format(inc, abs(means[-2]-means[-1]))
        if len(means) < 3: inc = ''
        print('---------------------------------------')
        print('Mean at prev gen: {:.3f}{}'.format(means[-1], inc))
        print('            GENERATION {}'.format(g+1))
        print('---------------------------------------')
        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))

        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < cxpb:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        for mutant in offspring:
            if random.random() < mutpb:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        for ind in offspring:
            for n in range(0, IND_size):
                if ind[n] < 0: ind[n] = 0 + random.random()/10
                if ind[n] > 1: ind[n] = 1 - random.random()/10

        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = (fit,)
        fitnesses = [ind.fitness.values[0] for ind in pop]
        means.append(sum(fitnesses) / len(fitnesses))
        pop[:] = offspring
    return pop, means[1:]




def run_EvolutiveAlgorithm(pop_size, ngen, target, cxpb = 0.7, mutpb = 0.5):
    global IND_size
    global maxLoss
    global TARGET
    IND_size = 10  # n_hyperParameters
    maxLoss = 1000000  # maximum loss function value
    TARGET = target

    creator.create("Fitness", base.Fitness, weights=(-1.0,))
    creator.create("Individual", list, fitness=creator.Fitness)

    toolbox = base.Toolbox()
    toolbox.register("attr_float", random.random)
    toolbox.register("individual", tools.initRepeat, creator.Individual, createRandomParameters, n=IND_size)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=1, indpb=0.1)
    toolbox.register("select", tools.selTournament, tournsize=3)
    toolbox.register("evaluate", evaluate_)

    fun.initializeDatasets()

    pop, trend = evolution(toolbox, pop_size=pop_size, ngen=ngen, target=target, cxpb=cxpb, mutpb=mutpb)

    fitness_min = maxLoss
    champion = []
    for ind in pop:
        if(ind.fitness.values[0]< fitness_min):
            fitness_min = ind.fitness.values[0]
            champion=ind
    plt.plot(list(range(len(trend))), trend)
    #plt.show()

    print('--------\nEvolutive algorithm trend: {}\n diff: {}'.format(
                                                [float('{:.3f}'.format(trend[i])) for i in range(0, len(trend))],
                                                [float('{:.3f}'.format(trend[i]-trend[i-1])) for i in range(1, len(trend))]))
    print('--------\nBest genome --> Score: {}\n{}\n--------'.format(champion.fitness.values[0], champion))
