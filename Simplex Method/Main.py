import Problems as PB
import SimplexAlgorithm as SA

def main():
    '''Defining the linear programming problem'''
    LPP = PB.LinearProgrammingProblem()
    LPP.costX(1, 5).costX(2, 5).costX(3, 5).operate('max')
    #LPP.newEq().plusX(1, 1).plusX(2, 2).plusX(3, 3).operate('=', 4)
    #LPP.newEq().plusX(1, 6).plusX(2, 7).operate('>=', 6)
    LPP.newEq().plusX(1, 6).plusX(2, 3).operate('<=', 6)
    LPP.newEq().plusX(1, 6).plusX(3, 10).operate('<=', 6)
    LPP.newEq().plusX(1, 4).plusX(2, -13).operate('<=', 4)
    LPP.NNconstraints([1, 3])
    LPP.print()

    '''Standardize and check for trivial solutions (by throwing an exception)'''
    SLPP = LPP.standardize()
    SLPP.print(LPP)

    simplex = SA.Simplex(SLPP)
    simplex.run()




if __name__ == '__main__':
    main()
