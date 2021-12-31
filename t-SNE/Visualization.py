import matplotlib
import numpy as np
import itertools
from matplotlib.animation import FuncAnimation as FA
from matplotlib.animation import FFMpegWriter as FFMW
from matplotlib import pyplot as plt

matplotlib.rcParams['animation.ffmpeg_path'] = r'bin\\ffmpeg.exe'


def createFig():
    """
    It creates a figure to use in matplotlib
    """

    fig = plt.figure(figsize=(10, 5), edgecolor='black')
    fig.patch.set_facecolor('black')
    return fig


def setProperties(ax):
    """
    It sets the properties of the plot in matplotlib

    :param ax: axis
    """

    ax.patch.set_facecolor('black')
    ax.spines['bottom'].set_color('white')
    ax.spines['top'].set_color('white')
    ax.spines['left'].set_color('white')
    ax.spines['right'].set_color('white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')


def createAx(no_dims):
    """
    It sets the number of axis of the plot.

    :param no_dims: number of axis
    """

    if no_dims == 3:
        ax = plt.axes(projection='3d')
        ax.view_init(30, 45)
        return ax
    else:
        return plt.axes()


def plot(X, target, var=[], no_dims=3, show=True, ax=None,
         fig=None, iter_=-1, C=-1, leg=True, title=None):
    """
    Plots the given data in the number of dimensions given.

    :param X: the data
    :param target: target labels
    :param var: matrix of variances
    :param no_dims: number of dimensions for the plot
    :param show: if True shows the plot
    :param ax: matplotlib axis
    :param fig: matplotlib figure
    :param iter_: current iteration
    :param C: value cost function
    :param leg: legend on
    :param title: plot title
    """

    no_dims = min(no_dims, X.shape[1])
    if fig is None and ax is None:
        createFig()

    if ax is None:
        ax = createAx(no_dims)

    if len(var) == 0 or np.all(var == var[0]):
        var = 4
    else:
        var = var + np.abs(min(var))
        var = var * 40 / np.abs(max(var)) + 1

    if title is None:
        title = f'n={len(X)}'
    ax.set_title(title, color='white')
    setProperties(ax)

    col = plt.get_cmap('Paired').colors
    indexes = {}
    for i in range(len(target)):
        indexes[target[i]] = indexes.get(target[i], []) + [i]
    indexes = dict(sorted(indexes.items()))
    classes = dict(zip(indexes.keys(), range(1, len(indexes.keys()) + 1)))

    for k in indexes.keys():
        n = classes[k]
        args = {'color': col[n], 'marker': 'o'}
        if no_dims == 3:
            args['xs'] = X[indexes[k], 0]
            args['ys'] = X[indexes[k], 1]
            args['zs'] = X[indexes[k], 2]
        elif no_dims == 2:
            args['x'] = X[indexes[k], 0]
            args['y'] = X[indexes[k], 1]
        if type(var) == int:
            args['s'] = var
        else:
            args['s'] = var[indexes[k]]
        ax.scatter(**args)

    if leg:
        l = ax.legend(classes.keys(), loc="upper left", title="Classes", bbox_to_anchor=(1.01, 1),
                      borderaxespad=0., markerscale=3.)
        for handle in l.legendHandles:
            handle.set_sizes([24.0])

    if iter_ > -1 and C > -1:
        text = f'Iteration {iter_}\nLoss: {C}'
        if no_dims == 3:
            ax.text(0, 0, 0, s=text, style='italic', transform=ax.transAxes,
                    size=14, c='w', horizontalalignment='left', verticalalignment='top')
        else:
            ax.text(0.0, 1.13, s=text, style='italic', transform=ax.transAxes,
                    size=12, c='w', horizontalalignment='left', verticalalignment='top')
    if show:
        plt.show()
    return ax


def animation(tsne, target, var=False, title=None, ax=None,
              tsne2=None, target2=None, var2=False, title2=None, ax2=None,
              fig=None, save=''):
    """
    It creates an animation of the evolution of the clusters found by the t-SNE method.

    :param tsne: t-SNE istance
    :param target: target labels
    :param var: matrix of variances
    :param title: title of the plot
    :param tsne2: second t-SNE istance (optional)
    :param target2: target labels of the second tSNE istance
    :param var2: matrix of variances of the second tSNE istance
    :param title2: title of the second plot
    :param ax: axis on which this method will draw the first plot
    :param ax2: axis on which this method will draw the second plot
    :param fig: figure on which this method will draw
    :param save: path to save the animation
    """

    data_array = tsne.Y_hist
    sigma = tsne.sigma
    sigma2 = []
    no_dims = data_array[0].shape[1]
    no_dims2 = -1

    if tsne2 is not None:
        data_array2 = tsne2.Y_hist
        no_dims2 = data_array2[0].shape[1]
        sigma2 = tsne2.sigma

    if not var:
        sigma = []
    if not var2:
        sigma2 = []

    nF = len(data_array)
    if no_dims == 3 or no_dims2 == 3:
        nF += 200

    if fig is None and ax is None:
        fig = createFig()

    projection = None
    if no_dims == 3:
        projection = '3d'

    leg=True
    if no_dims2 == -1:
        ax = fig.add_subplot(1, 1, 1, projection=projection)
    else:
        leg = False
        if ax is None:
            ax = fig.add_subplot(1, 2, 1, projection=projection)

        projection = None
        if no_dims2 == 3:
            projection = '3d'
        if ax2 is None:
            ax2 = fig.add_subplot(1, 2, 2, projection=projection)

    if no_dims == 3:
        ax.view_init(30, 45)
    if no_dims2 == 3:
        ax2.view_init(30, 45)

    def animate(i):
        """
        It adds the frame of the ith iteration.

        :param i: ith iteration
        """

        ax.cla()
        if i >= len(data_array):
            plot(data_array[-1], target, no_dims=no_dims, ax=ax, fig=fig, var=sigma,
                 show=False, iter_=len(data_array), C=tsne.C_hist[-1], leg=leg, title=title)
            if no_dims == 3:
                ax.view_init(30, i - len(data_array) + 45)
        else:
            plot(data_array[i], target, no_dims=no_dims, ax=ax, fig=fig, var=sigma,
                 show=False, iter_=i, C=tsne.C_hist[i], leg=leg, title=title)

        if no_dims2 != -1:
            ax2.cla()
            if i >= len(data_array2):
                plot(data_array2[-1], target2, no_dims=no_dims2, ax=ax2, fig=fig, var=sigma2,
                     show=False, iter_=len(data_array2), C=tsne2.C_hist[-1], title=title2)
                if no_dims2 == 3:
                    ax2.view_init(30, i - len(data_array2) + 45)
            else:
                plot(data_array2[i], target2, no_dims=no_dims2, ax=ax2, fig=fig, var=sigma2,
                     show=False, iter_=i, C=tsne2.C_hist[i], title=title2)

    animation = FA(fig, animate, frames=nF, interval=50)
    if save != '':
        if no_dims == 3 or no_dims2 == 3:
            save = save.replace('.', '3D.')
        print(f'\nSaving video as {save}\n...')
        f = f'{save}'
        writer = FFMW(fps=8)
        animation.save(f, writer=writer, dpi=400)
        print('Successfully saved!')
    else:
        plt.show()


def plotRegions2D(data, cluster, type, ax=None, leg=False, title=None, show=False):

    if data.Y_train.shape[1] != 2:
        return None

    density = 200
    if ax is None:
        fig = createFig()
        ax = fig.add_subplot(1, 1, 1, projection=None)
        density *= 2
        leg = True

    if type == 'train':
        plot(data.Y_train, target=data.target_train, ax=ax, leg=False, show=False)
    elif type == 'test':
        plot(data.Y_test, target=data.target_test, ax=ax, leg=False, show=False)

    dx = np.linspace(ax.get_xbound()[0], ax.get_xbound()[1], density)
    dy = np.linspace(ax.get_ybound()[0], ax.get_ybound()[1], density)
    m = np.array([x for x in itertools.product(dx, dy)])

    indexes = np.unique(data.target_train)
    indexes.sort()

    col = plt.get_cmap('Paired').colors
    classes = dict(zip(indexes, range(1, len(indexes) + 1)))

    prediction = cluster.predict(m)
    c = np.array(list(map(lambda x: col[classes[x]], prediction)))
    ax.scatter(m[:, 0], m[:, 1], s=2, c=c, alpha=0.1)

    if type == 'train':
        plot(data.Y_train, target=data.target_train, ax=ax, leg=leg, title=title, show=show)
    elif type == 'test':
        plot(data.Y_test, target=data.target_test, ax=ax, leg=leg, title=title, show=show)


def plotMap2D(data, cluster, type):
    if data.Y_train.shape[1] != 2:
        return None
    fig = createFig()
    ax = fig.add_subplot(1, 2, 1, projection=None)
    ax2 = fig.add_subplot(1, 2, 2, projection=None)
    plotRegions2D(data, cluster, type=type, ax=ax, show=False, title='Map 2D')
    if type == 'train':
        plot(data.Y_train, target=data.target_train, ax=ax2, show=True)
    elif type == 'test':
        plot(data.Y_test, target=data.target_test, ax=ax2, show=True)


