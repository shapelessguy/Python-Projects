import sys
import numpy as np
from matplotlib import pyplot as plt
import math


def rosenbrock(x, a=1, b=100):
    x1, x2 = x
    value = b * (x1 ** 2 - x2) ** 2 + (a - x1) ** 2
    diff = np.array([400 * x1 ** 3 - 400 * x1 * x2 - 2 * (1 - x1), - 200 * (x1 ** 2 - x2)])
    H = np.array([[400 * (x1 ** 2 - x2) + 800 * x1 ** 2 + 2, - 400 * x1], [-400 * x1, 200]])
    return value, diff, H


def sec_function(x):
    x1, x2 = x
    value = (x2 - x1) ** 4 + 8 * x1 * x2 - x1 + x2 + 3
    diff = np.array([-4 * (x2 - x1) ** 3 + 8 * x2 - 1, 4 * (x2 - x1) ** 3 + 8 * x1 + 1])
    H = np.array([[12 * (x2 - x1) ** 2, 8 - 12 * (x2 - x1) ** 2], [8 - 12 * (x2 - x1) ** 2, 12 * (x2 - x1) ** 2]])
    return value, diff, H


class Function:
    def __init__(self, function):
        self.function = function

    def compute(self, x):
        y = self.function(x)
        self.value = y[0]
        self.diff = y[1]
        self.H = y[2]
        return self.value

    def normalize(self):
        self.diff_norm = self.diff / np.sqrt(np.sum(np.power(self.diff, 2)))

    def backtracking(self, x0, p, alpha=1.0, beta=0.5, max_iter=1000, execute=True):
        if not execute:
            return alpha, 0
        f0 = self.compute(x0)
        x1 = x0 + alpha * p
        f1 = self.compute(x1)
        iterations = 1
        while f1 > f0 and iterations < max_iter:
            alpha *= beta
            x1 = x0 + alpha * p
            f1 = self.compute(x1)
            iterations += 1
        return alpha, iterations

    def bracketing(self, x, max_iterations, delta):
        r = (math.sqrt(5) + 1) / 2
        self.compute(x)
        self.x_experience = [list(x) + [self.value]]
        self.normalize()
        p = - self.diff_norm
        x1 = x + delta * p
        x2 = x + delta * r * p
        f1 = self.compute(x1)
        self.x_experience.append(list(x1) + [f1])
        f2 = self.compute(x2)
        iterations = 1
        while f2 < f1 and iterations < max_iterations:
            iterations += 1
            x1 = x2
            f1 = f2
            p = - self.diff
            x2 = x + delta * (r ** iterations) * p
            self.x_experience.append(list(x1) + [f1])
            f2 = self.compute(x2)
            sys.stdout.write(f'\r--- Bracketing - Iteration number {iterations} ---')
            sys.stdout.flush()
        print(f'\r--- Bracketing - Iteration number {iterations} ---')
        return self.x_experience

    def newton_raphson(self, x, max_iterations, tolerance, BT):
        self.compute(x)
        iterations = 1
        sub_iterations = 0
        self.x_experience = [x + [self.value]]
        while max(abs(self.diff)) > tolerance and iterations < max_iterations:
            self.normalize()
            p = - np.dot(np.linalg.inv(self.H), self.diff_norm)
            alpha, additional_iterations = self.backtracking(x, p, max_iter=max_iterations, execute=BT)
            x = x + alpha * p
            self.compute(x)
            self.x_experience.append(list(x) + [self.value])

            iterations += 1
            sub_iterations += additional_iterations
            sys.stdout.write(
                f'\r--- Newton/Raphson - Iteration number {iterations} and {sub_iterations} sub-iterations ---')
            sys.stdout.flush()
        subit_str = ''
        if BT:
            subit_str = ' and ' + str(sub_iterations) + ' sub-iterations ---'
        print(f'\r--- Newton/Raphson - Iteration number {iterations}' + subit_str)
        return self.x_experience

    def steepest_descent(self, x, max_iterations, tolerance, delta, BT):
        self.compute(x)
        self.normalize()
        iterations = 1
        sub_iterations = 0
        self.x_experience = [x + [self.value]]
        while max(abs(self.diff_norm)) > tolerance and iterations < max_iterations:
            p = - self.diff_norm
            alpha, additional_iterations = self.backtracking(x, p, max_iter=max_iterations, alpha=delta, execute=BT)
            x = x + alpha * p
            y = self.compute(x)
            self.normalize()
            self.x_experience.append(list(x) + [y])

            iterations += 1
            sub_iterations += additional_iterations
            sys.stdout.write(
                f'\r--- Steepest descent - Iteration number {iterations} and {sub_iterations} sub-iterations ---')
            sys.stdout.flush()
        subit_str = ''
        if BT:
            subit_str = ' and ' + str(sub_iterations) + ' sub-iterations ---'
        print(f'\r--- Steepest descent - Iteration number {iterations}' + subit_str)
        return self.x_experience

    def minimum(self, method, x, max_iterations=1000, delta=10 ** -3, tolerance=10 ** -3, BT=True):
        if method == 'newton_raphson':
            return self.newton_raphson(x, max_iterations=max_iterations, tolerance=tolerance, BT=BT)
        elif method == 'bracketing':
            return self.bracketing(x, max_iterations=max_iterations, delta=delta)
        elif method == 'steepest_descent':
            return self.steepest_descent(x, max_iterations=max_iterations, tolerance=tolerance, delta=delta, BT=BT)


def plot_minimum(f, ax, experience, n_points=200, offset=15, title=''):
    exp = np.array(experience).T.copy()

    x1 = np.linspace(np.min(exp[0]) - offset, np.max(exp[0]) + offset, n_points)
    x2 = np.linspace(np.min(exp[1]) - offset, np.max(exp[1]) + offset, n_points)
    x3 = np.array([[f.compute([x, y]) for x in x1] for y in x2])
    x1, x2 = np.meshgrid(x1, x2)

    ax.view_init(40, 80)

    ax.plot_surface(x1, x2, x3, alpha=0.9, zorder=-1)
    ax.plot(exp[0], exp[1], exp[2], c='purple', marker='o', markersize=2, zorder=10)
    ax.plot([exp[0][0]], [exp[1][0]], [exp[2][0]], c='blue', marker='o', zorder=10)
    ax.plot([exp[0][-1]], [exp[1][-1]], [exp[2][-1]], c='red', marker='o', zorder=10)
    ax.set_title(title, size=14)
    return ax


def main():
    f = Function(sec_function)
    initialPoint = [-1, 1]
    plt.figure(figsize=(10, 5))
    graph_offset = 1

    exp_bracketing = f.minimum('bracketing', initialPoint)
    bracketing_min = np.round(exp_bracketing[-1][:-1], 4)
    plot_minimum(f, plt.subplot(321, projection='3d'), exp_bracketing, offset=graph_offset,
                 title='Bracketing Minimum: {}'.format(bracketing_min))

    exp_newton = f.minimum('newton_raphson', initialPoint, BT=False)
    newton_min = np.round(exp_newton[-1][:-1], 4)
    plot_minimum(f, plt.subplot(322, projection='3d'), exp_newton, offset=graph_offset,
                 title='Newton-Raphson Minimum: {}'.format(newton_min))

    exp_descent = f.minimum('steepest_descent', initialPoint, BT=False)
    descent_min = np.round(exp_descent[-1][:-1], 4)
    plot_minimum(f, plt.subplot(323, projection='3d'), exp_descent, offset=graph_offset,
                 title='Steepest Descent Minimum: {}'.format(descent_min))

    exp_newton = f.minimum('newton_raphson', initialPoint)
    newton_min = np.round(exp_newton[-1][:-1], 4)
    plot_minimum(f, plt.subplot(324, projection='3d'), exp_newton, offset=graph_offset,
                 title='Newton-Raphson (backtracking) Minimum: {}'.format(newton_min))

    exp_descent = f.minimum('steepest_descent', initialPoint)
    descent_min = np.round(exp_descent[-1][:-1], 4)
    plot_minimum(f, plt.subplot(325, projection='3d'), exp_descent, offset=graph_offset,
                 title='Steepest Descent (backtracking) Minimum: {}'.format(descent_min))

    plt.show()


main()

