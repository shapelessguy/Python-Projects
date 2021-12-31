
class Node:

    def __init__(self, id):
        self.id = id
        self.routingTable = []
        self.links = []  # links to the neighbors
        self.N = []  # neighbors
        self.toSend = []  # messages to send to the neighbors - same format as routing Table
        self.previousMinimum = []
        self.subnet = 0

    def findNeighbor(self):
        for link in self.links:
            if link.association[0].id == self.id:
                self.N.append(link.association[1])
            elif link.association[1].id == self.id:
                self.N.append(link.association[1])

    def computeMinimum(self):
        destinations = []
        for entry in self.routingTable:
            if entry[0] not in destinations:
                destinations.append(entry[0])
            if entry[1] not in destinations:
                destinations.append(entry[1])
        interestingDistances = []
        for destination in destinations:
            sums = []
            for intermediate in destinations:
                found1 = False
                found2 = False
                sum = 0
                for i in range(len(self.routingTable)):
                    if self.id == intermediate:
                        found1 = True
                        break
                    if (self.routingTable[i][0] == self.id and self.routingTable[i][1] == intermediate):
                        sum += self.routingTable[i][2]
                        found1 = True
                        break
                for i in range(len(self.routingTable)):
                    if destination == intermediate:
                        found2 = True
                        break
                    if (self.routingTable[i][0] == intermediate and self.routingTable[i][1] == destination):
                        sum += self.routingTable[i][2]
                        found2 = True
                        break
                if found1 and found2:
                    sums.append((sum, intermediate))
                #print(self.id, intermediate, destination, sums)
            if len(sums)>0:
                #minimum = min([i for i, j in sums])
                interestingDistances.append([self.id, destination, min([i for i,j in sums])])
        return interestingDistances

    def compute(self, from_id, distanceVector):
        for entry in self.routingTable:
            if entry[0] == from_id:
                self.routingTable.remove(entry)
        for distance in distanceVector:
            for route in self.routingTable:
                if route[0] == from_id and route[1] == distance[0]:
                    self.routingTable.remove(route)
            self.routingTable.append([from_id, distance[0], distance[1]])
            found = False
            for route in self.routingTable:
                if route[0] == distance[0] and route[1] == from_id:
                    found = True
            if not found:
                self.routingTable.append([distance[0], from_id, distance[1]])
        minimumVector = self.computeMinimum()
        equal = True
        if len(minimumVector) != len(self.previousMinimum):
            equal = False
        else:
            for element in minimumVector:
                if element not in self.previousMinimum:
                    equal = False
        if equal:
            return -1

        self.previousMinimum = minimumVector[:]
        for entry in self.routingTable:
            if entry[0] == self.id:
                self.routingTable.remove(entry)
        for entry in minimumVector:
            for route in self.routingTable:
                if route[0] == entry[0] and route[1] == entry[1]:
                    self.routingTable.remove(route)
            self.routingTable.append(entry)
            for entry1 in self.toSend:
                if entry1[0]==entry[0] and entry1[1]==entry[1]:
                    self.toSend.remove(entry1)
            self.toSend.append(entry)
        return

    def initialize(self, distanceVector):
        for distance in distanceVector:
            self.routingTable.append([self.id, distance[0], distance[1]])
            self.toSend.append([self.id, distance[0], distance[1]])


    def send(self):
        alterToSend = self.toSend[:]
        logs = []
        self.toSend = []
        for link in self.links:
            neighbor = link.other(self.id)
            if neighbor == self.id:
                return
            distanceVector = []
            for entry in alterToSend:
                distanceVector.append((entry[1], entry[2]))

            #print('sender', self.id, 'to', neighbor.id)
            if len(distanceVector) > 0:
                logs.append((neighbor.id, len(distanceVector)))
                neighbor.compute(self.id, distanceVector)  # send a distance vector (from_id, list[to_id, cost])
        return logs

    def addRoutingTable(self, obj):
        if obj[0] < obj[1]:
            first = obj[0]
            second = obj[1]
        else:
            second = obj[0]
            first = obj[1]
        self.routingTable.append([first, second, obj[2]])

    def printAssociations(self):
        for link in self.links:
            if link.association[0].id == self.id:
                link.print()
            elif link.association[1].id == self.id:
                link.print(True)

    def printRouting(self):
        print('Routing Table for Node:', self.id)
        self.routingTable.sort(key=takeSecond)
        self.routingTable.sort(key=takeFirst)
        for elem in self.routingTable:
            print(elem)

    def printToSend(self):
        for elem in self.toSend:
            print(elem)

def takeFirst(elem):
    return elem[0]
def takeSecond(elem):
    return elem[1]