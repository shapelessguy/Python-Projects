import numpy as np
import time
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


class Equation:
    def __init__(self):
        self.maxIndex = 0
        self.values = {}
        self.op = ''
        self.b = 0
        return

    def plusX(self, index, value):
        self.values[index] = self.values.get(index, 0) + value
        if self.maxIndex < index:
            self.maxIndex = index
        return self

    def operate(self, operation, value):
        self.b = value
        self.op = operation
        if operation == '>=': self.op = '≥'
        if operation == '<=': self.op = '≤'
        return self

    def order(self):
        self.values = {k: v for k, v in sorted(self.values.items(), key=lambda item: item[0])}

    def toString(self):
        output = ' + '.join([str(item[1])+'x'+str(item[0]).translate(SUB) for item in self.values.items()])
        output = output.replace(' 1x', ' x').replace(' -1x', ' -x').replace('+ -', '- ')
        if self.op in ['min', 'max']:
            return self.op + ' z(x) = ' + output
        else:
            output = '   ' + output + ' ' + self.op + ' ' + str(self.b)
            return output


class LinearProgrammingProblem:
    def __init__(self):
        self.costFunction = Equation()
        self.NNvariables = []
        self.equations = []
        self.maxIndex = 0
        self.substitutions = {}

    def newEq(self):
        self.equations.append(Equation())
        return self.equations[-1]

    def costX(self, index, value):
        self.costFunction.plusX(index, value)
        return self

    def operate(self, operation):
        self.costFunction.operate(operation, 0)

    def NNconstraints(self, list):
        for el in list:
            self.NNvariables.append(el)

    def getMaxIndex(self):
        self.maxIndex = max([element.maxIndex for element in self.equations])
        self.maxIndex = max([self.maxIndex]+self.NNvariables+[self.costFunction.maxIndex])

    def transformObjectiveFunction(self):
        if self.costFunction.op == 'max':
            self.costFunction.op = 'min'
            for item in self.costFunction.values.items():
                self.costFunction.values[item[0]] = -item[1]

    def changeKnownTermSign(self):
        for equation in self.equations:
            if equation.b < 0:
                if equation.op == '≥':
                    equation.op = '≤'
                elif equation.op == '≤':
                    equation.op = '≥'
                for item in equation.values.items():
                    equation.values[item[0]] = -item[1]
                equation.b = -equation.b

    def orderEquations(self):
        buffer = []
        for equation in self.equations:
            if equation.op == '≤':
                buffer.insert(0, equation)
            else:
                buffer.append(equation)
        self.equations = buffer

    def introduceSurplus_SlackVariables(self, op):
        for equation in self.equations:
            coeff = 0
            if op == '≥' and equation.op == '≥': coeff = -1
            if op == '≤' and equation.op == '≤': coeff = 1
            if coeff != 0:
                equation.op = '='
                self.getMaxIndex()
                equation.plusX(self.maxIndex+1, coeff)
                self.NNvariables.append(self.maxIndex+1)

    def imposeNNconstraints(self):
        for index in range(1, self.maxIndex):
            if index not in self.NNvariables:
                self.getMaxIndex()
                self.NNvariables.append(index)
                self.NNvariables.append(self.maxIndex+1)
                self.substitutions[index] = (index, -(self.maxIndex+1))
                for equation in self.equations:
                    if index in equation.values:
                        equation.plusX(self.maxIndex+1, -equation.values[index])
                value = self.costFunction.values.get(index, 0)
                if value>0:
                    self.costFunction.plusX(self.maxIndex+1, -value)

    def standardize(self):
        self.orderEquations()
        self.transformObjectiveFunction()
        self.changeKnownTermSign()
        self.introduceSurplus_SlackVariables('≥')
        self.imposeNNconstraints()
        self.introduceSurplus_SlackVariables('≤')
        self.getMaxIndex()
        return StandardizedLPP(self)

    def print(self, title='----NATURAL----'):
        print(title)
        self.costFunction.order()
        self.NNvariables = sorted(self.NNvariables)
        print(self.costFunction.toString())
        for eq in self.equations:
            eq.order()
            print(eq.toString())
        if len(self.NNvariables) > 0:
            print(' x'+',x'.join([str(element).translate(SUB) for element in self.NNvariables]) + ' ≥ 0')
        print()
        time.sleep(0.1)


class StandardizedLPP:
    def __init__(self, LPP):
        self.m = len(LPP.equations)
        self.n = LPP.maxIndex
        if self.m >= self.n:
            raise Exception('n should be greater than m')
        buffer = []
        for equation in LPP.equations:
            buffer.append([])
            for index in range(1, LPP.maxIndex+1):
                buffer[-1].append(equation.values.get(index,0))
        self.A = np.array(buffer)

        '''Check on rank'''
        self.rank = np.linalg.matrix_rank(self.A)
        if self.rank != self.m:
            raise Exception('Rank of the A matrix is less than m')

        '''Check on null columns'''
        if np.any(self.A.sum(axis=0) == 0):
            raise Exception('Null column in A matrix')

        buffer = []
        for equation in LPP.equations:
            buffer.append([equation.b])
        self.b = np.array(buffer)
        buffer = []
        for index in range(1, self.n + 1):
            buffer.append([LPP.costFunction.values.get(index,0)])
        self.c = np.array(buffer)
        time.sleep(0.1)

    def print(self, LPP=None):
        if LPP is not None:
            LPP.print(title='----STANDARD----')
        print('c terms:')
        print(self.c.transpose())
        print('A matrix:')
        print(self.A)
        print('b terms:')
        print(self.b.transpose())

