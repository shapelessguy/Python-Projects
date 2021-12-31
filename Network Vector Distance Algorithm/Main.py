import threading
import Network as Net
import matplotlib.pyplot as plt
import numpy as np
import Node
import Link
import random
import time

def runNetwork(net, showGraphics = True, oneNode = False, verbose=False):
    net = net
    globalNodeLoad, globalLinkLoad = net.initializeStats()
    activity = []
    iterations = 0
    if verbose:
        for node in net.nodes:
            node.printRouting()
    for i in range(100):
        nodeLoad, linkLoad = net.performStep()
        sumMessages = sum(linkLoad.values())
        if sumMessages == 0:
            iterations = i
            break
        for key in globalNodeLoad:
            globalNodeLoad[key].append(nodeLoad[key])
        for key in globalLinkLoad:
            globalLinkLoad[key].append(linkLoad[key])
        activity.append(sumMessages)
    activity_perLink = [sum(value) for value in globalLinkLoad]
    print('-------------------------------------------------------------')
    print('Network parameters:')
    print('nodes =', net.n, ', average connections:', net.averageConnections, ', max connections:', net.maxConnections)
    print('         Link number:', len(linkLoad), ', subnet count:', max([v.subnet for v in net.nodes]))
    print('         Iterations count:', iterations)
    print('         Total of messages shared:', sum(activity))
    if verbose:
        for node in net.nodes:
            node.printRouting()
    x = [i for i in range(len(activity_perLink))]
    t = [i for i in range(len(activity))]
    y = activity_perLink
    y2 = activity
    if showGraphics:
        plt.plot(t, y2)
        label = 'Activity along time'
        if oneNode:
            label = 'Activity along time - After Node addition'
        plt.title(label, fontdict=None, loc='center')
        plt.fill_between(t, y2)
        plt.show()
    return sum(activity)

def runSingleNetwork(quantity, averageConnections, maxConnections, showGraphics, verbose = True):
    net = Net.Network(quantity=quantity, averageConnections=averageConnections, maxConnections=maxConnections)
    runNetwork(net=net, showGraphics=showGraphics, verbose=verbose)
    net.addNode(connections=5)
    runNetwork(net=net, showGraphics=showGraphics, oneNode=True)

def runMultipleNetworks(from_, to_, averageConnections, maxConnections, showGraphics, computation = False):
    x = [i for i in range(from_, to_)]
    activity = []
    timeB = []
    for i in x:
        time1 = time.time()
        net = Net.Network(quantity=i, averageConnections=averageConnections, maxConnections=maxConnections)
        activity.append(runNetwork(net=net, showGraphics=False))
        timeB.append(time.time() - time1)
    activity_perNode = []
    for i in range(len(x)):
        activity_perNode.append(activity[i] / x[i])
    if showGraphics:
        plt.plot(x, activity)
        plt.title('Messages all over the network', fontdict=None, loc='center')
        plt.show()
        plt.plot(x, activity_perNode)
        plt.title('Activity per node', fontdict=None, loc='center')
        plt.yticks([i for i in range(0, int(max(activity_perNode)+1))])
        plt.show()
    if computation:
        plt.plot(x, timeB)
        plt.title('Computational time', fontdict=None, loc='center')
        plt.show()
    return activity, activity_perNode

def averageMultipleNetworks(runs, from_, to_, averageConnections, maxConnections, showGraphics = False):
    x = [i for i in range(from_, to_)]
    y1 = []
    y2 = []
    for i in range(runs):
        r1, r2 = runMultipleNetworks(from_=from_, to_=to_,averageConnections=averageConnections,
                                     maxConnections=maxConnections, showGraphics=showGraphics)
        y1.append(r1)
        y2.append(r2)
    npy1 = np.array(y1).sum(axis=0)/len(y1)
    npy2 = np.array(y2).sum(axis=0)/len(y2)
    plt.plot(x, npy1)
    plt.title('Messages all over the network - Mean', fontdict=None, loc='center')
    plt.show()
    plt.plot(x, npy2)
    plt.title('Messages per Node - Mean', fontdict=None, loc='center')
    plt.show()

def main():
    random.seed(4)
    runSingleNetwork(quantity=10, averageConnections=3, maxConnections=10, showGraphics=True, verbose=True)
    #runMultipleNetworks(from_=4, to_=20, averageConnections=3, maxConnections=10, showGraphics=True, computation=True)
    #averageMultipleNetworks(runs=30, from_=2, to_=18, averageConnections=3, maxConnections=10)


if __name__ == '__main__':
    main()
