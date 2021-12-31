from pip._vendor.colorama import Fore
import Inizializzazione

import Dataset as ds
import deap
import random
from deap import base
from deap import creator
from deap import tools
import matplotlib.pyplot as plt


range_lr = [0.001, 0.01]
perc_ev = 100
pop_size = 50
ngen = 15
epochs = 100 #Epoche rete neurale
B_size = 1024
string_save=''


train, y_train, test, y_test = ds.CreateDataset(perc_ev)
train_signal, train_background, test_signal, test_background = ds.Divide_datasets(train, y_train, test, y_test)
'''
ds.run_TrainandTest(
                    train, y_train, test, y_test,
                    train_signal, train_background, test_signal, test_background,
                    string_save='',
                    epochs=5,
                    lr=0.001,
                    B_size=2048,
                    DimRetSeqLayers=25,
                    DimNORetSeqLayers=25,
                    dropout1=0.3,
                    dropout2=0.3,
                    Params=1,
                    activation='sigmoid'
                    )
'''
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)


IND_size = 7
def Decodifica(n):
    if(n<0.3): return "sigmoid"
    if(n<0.6): return "relu"
    if(n<0.9): return "softmax"
    else: return "tanh"

def eval(individual, index, gen):

    if(index>-1):
        string_save = '_Gen' + str(gen) + '_ind' + str(index)
        print(Fore.GREEN + 'Gen: ' + str(gen) + '  - ind: ' +str(index)+ ' ->  '+str(individual))
        print(Fore.WHITE)
    else: string_save='None'
    lr = range_lr[0]+individual[0]*(range_lr[1]-range_lr[0])
    DimRetSeqLayers = (int)(1+individual[1]*40)
    DimNORetSeqLayers = (int)(1+individual[2]*40)
    dropout1 = individual[3]*0.8
    dropout2 = individual[3]*0.8
    Params = (int)(1 + individual[5]*4)
    activation = Decodifica(individual[6])

    return ds.run_TrainandTest(
                    train, y_train, test, y_test,
                    train_signal, train_background, test_signal, test_background,
                    epochs=epochs,
                    B_size=B_size,
                    string_save=string_save,
                    lr=lr,
                    DimRetSeqLayers=DimRetSeqLayers,
                    DimNORetSeqLayers=DimNORetSeqLayers,
                    dropout1=dropout1,
                    dropout2=dropout2,
                    Params=Params,
                    activation=activation
                    )

toolbox1 = base.Toolbox()
toolbox1.register("attr_float", random.random)
toolbox1.register("individual", tools.initRepeat, creator.Individual, toolbox1.attr_float, n=IND_size)
toolbox1.register("population", tools.initRepeat, list, toolbox1.individual)

toolbox1.register("mate", tools.cxTwoPoint)
toolbox1.register("mutate", tools.mutGaussian, mu=0, sigma=1, indpb=0.1)
toolbox1.register("select", tools.selTournament, tournsize=3)
toolbox1.register("evaluate", eval, index=0, gen=0)

def main(toolbox):
    pop = toolbox.population(n=pop_size)
    pop = Inizializzazione.Inizializza(pop)
    for ind in pop:
        print(ind[0])
    CXPB, MUTPB, NGEN = 0.7, 0.3, ngen
    print(Fore.GREEN + 'Generation 0')
    print(Fore.WHITE)
    fitnesses = list(map(toolbox.evaluate, pop))
    convergence=[]

    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = (fit,)

    for g in range(NGEN):

        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))

        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < CXPB:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        for mutant in offspring:
            if random.random() < MUTPB:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        for ind in offspring:
            for n in range(0, IND_size):
                if(ind[n]<0): ind[n]=0
                if(ind[n]>1): ind[n]=1
        index=0
        fitnesses=[]
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        for ind in invalid_ind:
            index+=1
            fitnesses.append(toolbox.evaluate(ind, index=index, gen=g+1))

        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = (fit,)

        convergence.append(sum(fitnesses)/len(fitnesses))
        plt.plot(convergence)
        plt.title('Evolutive algorithm')
        plt.ylabel('Efficiency')
        plt.xlabel('Epoch')
        plt.savefig('images/Evolutive_Algorithm.png', dpi=300)
        plt.close()

        pop[:] = offspring
    print('Result population at Generation '+str(g+1)+':')
    for ind in pop:
        print(str(ind)+',')

    return pop, convergence



pop, convergence = main(toolbox1)

fitness_max=0
campione = []

print('Result population:')
for ind in pop:
    print(str(ind) + '  acc: ' + str(ind.fitness.values[0]))
    if(ind.fitness.values[0]> fitness_max):
        fitness_max = ind.fitness.values[0]
        campione=ind


print("Genoma migliore:")
print(str(campione) + '  acc: ' + str(campione.fitness.values[0]))




