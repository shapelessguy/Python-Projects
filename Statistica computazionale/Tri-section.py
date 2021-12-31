#Claudio
import math

def function(x):
    return math.pow(x, 2) + 2*math.exp(-x)

def f2(x):
    return math.pow(x, 4) + math.exp(-x)

def derivate(function, value, x, step):
    return (function(x+step) - value)/step

def tri_section(x1, x2, function, epsilon, golden=False):
    n_iter = 0
    if golden:
        while x2-x1 > epsilon * 2:
            n_iter += 1
            R = (1+math.sqrt(5)) / 2
            interval = x2-x1
            x3 = x2 - interval/R
            x4 = x1 + interval/R
            if function(x4)-function(x3) > 0:
                x2 = x3
            else:
                x1 = x4
    else:
        delta = (x2 - x1)/3
        while x2-x1 > epsilon * 2:
            n_iter += 1
            x3 = x1 + delta
            x4 = x2 - delta
            if function(x4)-function(x3) > 0:
                x2 = x4
            else:
                x1 = x3
            delta = 2*delta/3

    err = (x2-x1)/2
    print('result: ', x1+err, 'error:', err, 'íterations:', n_iter)

def bracketing():
    return


def steepestD(x, function, tolerance):
    maxIter = 1000
    n_iter = 0
    alpha = 0.1
    d_fo = tolerance+1
    while n_iter < maxIter and math.fabs(d_fo) > tolerance:
        p = -d_fo
        x = x + alpha * p
        fo = function(x)
        d_fo = derivate(function, fo, x, step=0.001)
        n_iter += 1
    print('result: ', x, 'íterations:', n_iter)
    return

def backtracking():
    return

def newton_Raphson():
    return


def main():
    tri_section(0, 2, function, epsilon=math.pow(10, -6), golden=False)
    #steepestD(0, f2, tolerance=math.pow(10, -6))


if __name__ == '__main__':
    main()