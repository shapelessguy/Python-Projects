import Node as nd
import Link as lk
import random

#  minConnections = 1

#  random.seed(11)

class Network:

    def __init__(self, quantity, averageConnections, maxConnections):
        self.averageConnections = averageConnections
        self.maxConnections = maxConnections
        self.nodes = []  # Nodes collection
        self.links = []  # Links collection
        self.n = quantity  # number of nodes
        self.createNet(quantity)

    def createNet(self, n):
        self.createNodes(n)
        self.createLinks(self.nodes)

    def createNodes(self, n):
        for i in range(n):
            self.nodes.append(nd.Node(i))

    def createLinks(self, nodes):
        for i in range(len(nodes)):
            n = 0
            for j in range(i, len(nodes)):
                p = self.averageConnections/len(nodes)
                if random.random() < p and i != j and n < self.maxConnections:
                    self.links.append(lk.Link(nodes[i], nodes[j], random.randrange(1, 11)))
                    n += 1


        for index in range(len(nodes)):
            associations = lk.Association(index, self.links)
            if len(associations) == 0:
                listAvailable = [m for m in range(len(nodes)) if m != index]
                self.links.append(lk.Link(nodes[index], nodes[random.choice(listAvailable)], random.randrange(1, 11)))


        for index in range(len(nodes)):
            nodes[index].links = lk.Association(index, self.links)
        self.fixIsles()
        for index in range(len(nodes)):
            nodes[index].links = lk.Association(index, self.links)

        for index in range(len(nodes)):
            distanceVector = []
            for link in nodes[index].links:
                other = link.other(index)
                distanceVector.append((other.id, link.cost))
            nodes[index].initialize(distanceVector)
            #nodes[index].printRouting()    #  <--- Initial routing tables!

    def initializeStats(self):
        linkLoad = {}
        nodeLoad = {}
        for link in self.links:
            linkLoad[(link.association[0].id, link.association[1].id)] = []
        for node in self.nodes:
            nodeLoad[node.id] = []
        return nodeLoad, linkLoad

    def performStep(self):
        linkLoad = {}
        nodeLoad = {}
        for link in self.links:
            linkLoad[(link.association[0].id, link.association[1].id)] = 0
        for node in self.nodes:
            nodeLoad[node.id] = 0

        for index in range(len(self.nodes)):
            logs = self.nodes[index].send()
            if len(logs) > 0:
                for log in logs:
                    #globalLogs.append((index, log[0], log[1]))
                    pos_ass1 = (index, log[0])
                    pos_ass2 = (log[0], index)
                    nodeLoad[index] += 1
                    if linkLoad.get(pos_ass1, -1) != -1:
                        linkLoad[pos_ass1] += 1
                    else:
                        linkLoad[pos_ass2] += 1
        return nodeLoad, linkLoad

    def fixIsles(self):
        value = 0
        connected_indexes = []
        indexes = [i for i in range(len(self.nodes))]
        while len(indexes)>0:
            while len(connected_indexes)>0:
                for conn_index in connected_indexes:
                    for link in self.nodes[conn_index].links:
                        ass_id = link.other(conn_index).id
                        if ass_id in indexes:
                            self.nodes[ass_id].subnet = value
                            indexes.remove(ass_id)
                            connected_indexes.append(ass_id)
                    connected_indexes.remove(conn_index)
            if len(indexes)==0: break
            value = value+1
            in_i = random.choice(indexes)
            connected_indexes.append(in_i)
            indexes.remove(in_i)
            self.nodes[in_i].subnet = value
        nodes = {}
        for subnet in range(value):
            nodes[subnet] = []
            for node in self.nodes:
                if node.subnet == subnet+1:
                    nodes[subnet].append(node.id)
        couples = [(i,i+1) for i in range(value-1)]
        for subnet1, subnet2 in couples:
            self.links.append(lk.Link(self.nodes[random.choice(nodes[subnet1])], self.nodes[random.choice(nodes[subnet2])], random.randrange(1, 11)))


    def addNode(self, connections):
        self.nodes.append(nd.Node(len(self.nodes)))
        index = len(self.nodes)-1
        indexes = [i for i in range(len(self.nodes)-1)]
        for i in range(connections):
            rand = random.choice(indexes)
            indexes.remove(rand)
            randChoice = self.nodes[rand]
            self.links.append(lk.Link(self.nodes[index], randChoice, random.randrange(1, 11)))
        self.nodes[index].links = lk.Association(index, self.links)
        self.nodes[index].subnet = self.nodes[randChoice.id].subnet
        distanceVector = []
        for link in self.nodes[index].links:
            other = link.other(index)
            distanceVector.append((other.id, link.cost))
        self.nodes[index].initialize(distanceVector)