import numpy as np
import Utility as ut

class Simplex:
    def __init__(self, SLPP, mode='bland'):
        self.terminated = False
        self.mode = mode
        self.SLPP = SLPP
        self.A = ut.indexedNpArray(self.SLPP.A)
        self.c = ut.indexedNpArray(self.SLPP.c)
        self.initializeBase()

    def initializeBase(self):
        self.Bindexes = [i+1 for i in range(len(self.A.indexes)-self.A.matrix.shape[0], len(self.A.indexes))]
        self.NBindexes = [i+1 for i in range(len(self.A.indexes)-self.A.matrix.shape[0])]
        self.B = self.A.take(self.Bindexes)
        self.NB = self.A.take(self.NBindexes)
        self.cB = self.c.take(self.Bindexes)
        self.cNB = self.c.take(self.NBindexes)
        #self.SLPP.A = np.append(self.SLPP.A, np.eye(self.SLPP.m), axis=1)
        #self.SLPP.c = np.append(self.SLPP.c, np.ones(self.SLPP.m))
        #self.B = self.SLPP.A[0:, self.SLPP.n:].copy()
        #self.Bindexes = [i+self.SLPP.n+1 for i in range(self.SLPP.m)]
        return

    def run(self):
        iteration = Iteration(self)
        iteration.check()
        if self.terminated:
            return iteration.x_sol

class Iteration:
    def __init__(self, simplexState):
        self.state = simplexState
        self.state.terminated = False

    def check(self):
        self.phase1()
        self.phase2()
        if self.state.terminated: return

    def phase1(self):
        #Compute the base inverse
        self.state.Binv = np.linalg.inv(self.state.B)
        #Compute the associated solution
        self.state.x_sol = self.state.Binv.dot(self.state.SLPP.b)

    def phase2(self):
        self.p = self.state.cB.transpose().dot(self.Binv)
        self.c_red = self.p.dot(self.state.NB)
        if np.all(self.c_red >= 0):
            self.state.terminated = True
        if self.state.mode == 'bland':
            self.blandRule()
        #print(self.c_red)
        #print(self.notBindexes)
        #print(self.state.Bindexes)

    def blandRule(self):
        for index in range(len(self.notBindexes)):
            if self.c_red[index]<0:
                self.selectedIndex = self.notBindexes[index]
                break
        print(self.selectedIndex)

    def phase3(self):
        return

    def phase4(self):
        return

    def phase5(self):
        return

