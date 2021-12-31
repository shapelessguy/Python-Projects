
class Link:

    cost = -1  # infinite
    association = ()

    def __init__(self, node1, node2, cost):
        self.cost = cost
        self.association = (node1, node2)

    def other(self, id):
        if self.association[0].id == id:
            return self.association[1]
        elif  self.association[1].id == id:
            return self.association[0]

    def print(self, reverse = False):
        if reverse:
            id1 = self.association[1].id
            id2 = self.association[0].id
        else:
            id1 = self.association[0].id
            id2 = self.association[1].id

        print('node:', id1, '<-> node:', id2, 'at cost of:', self.cost)


def Association(index, links):
    indexAssociations = []
    for link in links:
        if link.association[0].id == index or link.association[1].id == index:
            indexAssociations.append(link)
    return indexAssociations

