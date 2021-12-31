import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


class PCAMethod:
    """
    It applies the PCA on the given data

    ...

    Attributes
    ----------
    X: numpy array
        data
    explainability: numpy array
        cumulative distribution of the
        variance explained in percentage
    """

    def __init__(self, X=np.array([]), expl_ratio=0.95):
        """
        Runs PCA on the NxD array X in order to reduce its dimensionality.
        """

        print("\nPreprocessing the data using PCA...")
        sc = StandardScaler()
        X = sc.fit_transform(X)
        pca = PCA()
        Y = pca.fit_transform(X)
        explained = np.cumsum(pca.explained_variance_ratio_)
        explaining = len(pca.explained_variance_[explained < expl_ratio])
        print(f"Only {explaining} features have been selected.")
        self.X = Y[:, :explaining]
        self.explainability = explained


class TSNE:
    """
    It applies the t-SNE method to a given dataset in order to cluster the data in lower dimensionalities

    ...

    Attributes
    ----------
    n: int
        number of observations
    P: numpy array
        probability matrix
    min_gain: float
        minimum gain
    in_momentum: float
        first momentum
    fin_momentum: float
        last momentum
    eta: float
        learning rate
    sigma: numpy array
        matrix of sigmas
    max_iter: int
        number of iterations
    X: numpy array
        data
    no_dims: int
        number of dimensions
    perplexity: float
        target perplexity
    C_hist: list
        loss function values throughout the iterations

    Methods
    -------
    run()
        encodes the a given string, otherwise it encodes the string 'hello'
    entropy(nodes, label, result, prefix='')
        assigns the code to each node of the Huffman binary tree
    binary_search_sigma()
        computes the average length of the code
    """

    def __init__(self, X, no_dims=2, perplexity=30.0):

        # Check inputs
        if isinstance(no_dims, float):
            print("Error: array X should have type float.")
            return -1
        if round(no_dims) != no_dims:
            print("Error: number of dimensions should be an integer.")
            return -1

        # Initialize variables
        (n, d) = X.shape

        self.n = n
        self.perplexity = perplexity
        self.no_dims = no_dims
        self.P = None
        self.min_gain = 0.01
        self.X = X
        self.Y_hist = None
        self.Y = None
        self.in_momentum = 0.5
        self.fin_momentum = 0.8
        self.eta = 500
        self.sigma = []
        self.iterations = 1000
        self.C_hist = []


    def computeP(self):
        P, sigma = self.binary_search_sigma(self.X, 1e-5, self.perplexity)
        P[np.isnan(P)] = 0.0
        P = P + np.transpose(P)
        P = P / np.sum(P)
        P = P * 4.									# early exaggeration
        P = np.maximum(P, 1e-12)
        self.P = P
        self.sigma = sigma


    def run(self, iterations=-1):
        """
        It runs the the t-SNE method on the given dataset with a given number of iterations. The other parameters
        are optimized iteration after iteration. At the end it reduces the dimensionality of the data (n,d) to
        the lower dimensionality (n,2).

        :param iterations: number of iterations
        :param eta: learning rate
        :param in_momentum: starting momentum (alpha)
        :param fin_momentum: ending momentum (alpha)
        """

        self.computeP()
        n = self.n
        no_dims = self.no_dims
        P = self.P
        P_real = (P / 4).copy()
        self.min_gain = 0.01
        if iterations > 0:
            self.iterations = iterations

        Y_array = []
        Y = np.random.randn(n, no_dims)
        dY = np.zeros((n, no_dims))
        iY = np.zeros((n, no_dims))
        gains = np.ones((n, no_dims))


        # Run iterations
        for iter in range(iterations):

            # Compute pairwise affinities
            sum_Y = np.sum(np.square(Y), 1)
            num = -2. * np.dot(Y, Y.T)
            num = 1. / (1. + np.add(np.add(num, sum_Y).T, sum_Y))
            num[range(n), range(n)] = 0.
            Q = num / np.sum(num)
            Q = np.maximum(Q, 1e-12)
            # Compute gradient
            PQ = P - Q
            for i in range(n):
                dY[i, :] = np.sum(np.tile(PQ[:, i] * num[:, i], (no_dims, 1)).T * (Y[i, :] - Y), 0)

            # Perform the update
            if iter < 20:
                momentum = self.in_momentum
            else:
                momentum = self.fin_momentum

            gains = (gains + 0.2) * ((dY > 0.) != (iY > 0.)) + (gains * 0.8) * ((dY > 0.) == (iY > 0.))
            gains[gains < self.min_gain] = self.min_gain
            iY = momentum * iY - self.eta * (gains * dY)
            Y = Y + iY
            Y = Y - np.tile(np.mean(Y, 0), (n, 1))
            Y_array.append(Y.copy())

            # Compute current value of cost function
            C = np.sum(P_real * np.log(P_real / Q))
            self.C_hist.append(round(C, 2))
            if (iter + 1) % 10 == 0:
                print("Iteration %d: error is %f" % (iter + 1, C))

            # Stop lying about P-values
            if iter == 100:
                P = P / 4.

        self.Y_hist = Y_array
        self.Y = Y_array[-1]

    def compute_perplexity(self, d=np.array([]), sigma=1.0):
        """
        It computes entropy and perplexity of the given i-th observation (array)

        :param d: i-th observation (array of the data)
        :param sigma: starting value of sigma
        :return: entropy and perplexity values (arrays)
        """

        # Compute P-row and corresponding perplexity
        p = np.exp(-d.copy() * sigma)
        sum_p = sum(p)
        if sum_p == 0:
            return 0, np.zeros(p.shape)
        h = np.log(sum_p) + sigma * np.sum(d * p) / sum_p
        p = p / sum_p
        return h, p

    def binary_search_sigma(self, x=np.array([]), tol=1e-5, perplexity=30.0):
        """
        It applies the binary search algorithm to find the value of sigma for each observation that allows to get
        the same perplexity of the given target.

        :param x: i-th observation (array of the data)
        :param tol: tolerable difference between computed and target perplexity
        :param perplexity: target perplexity value
        :return: probability matrix P, sigma
        """

        # Initialize some variables
        print("\nComputing pairwise distances...")
        (n, d) = x.shape
        sum_x = np.sum(np.square(x), 1)
        D = np.add(np.add(-2 * np.dot(x, x.T), sum_x).T, sum_x)
        P = np.zeros((n, n))
        beta_i = np.ones((n, 1))
        log_perplexity = np.log(perplexity)

        # Loop over all datapoints
        checkpoint = n / 6
        for i in range(n):

            # Print progress
            if int(i % checkpoint) == 0:
                print("Computing P-values for point %d of %d..." % (i, n))

            # Compute the Gaussian kernel and entropy for the current precision
            beta_min = -np.inf
            beta_max = np.inf
            Di = D[i, np.concatenate((np.r_[0:i], np.r_[i + 1:n]))]
            (H, thisP) = self.compute_perplexity(Di, beta_i[i])

            # Evaluate whether the perplexity is within tolerance
            h_diff = H - log_perplexity
            tries = 0
            while np.abs(h_diff) > tol and tries < 50:

                # If not, increase or decrease precision
                if h_diff > 0:
                    beta_min = beta_i[i].copy()
                    if beta_max == np.inf or beta_max == -np.inf:
                        beta_i[i] = beta_i[i] * 2.
                    else:
                        beta_i[i] = (beta_i[i] + beta_max) / 2.
                else:
                    beta_max = beta_i[i].copy()
                    if beta_min == np.inf or beta_min == -np.inf:
                        beta_i[i] = beta_i[i] / 2.
                    else:
                        beta_i[i] = (beta_i[i] + beta_min) / 2.

                # Recompute the values
                (H, thisP) = self.compute_perplexity(Di, beta_i[i])
                h_diff = H - log_perplexity
                tries += 1

            # Set the final row of P
            P[i, np.concatenate((np.r_[0:i], np.r_[i + 1:n]))] = thisP

        # Return final P-matrix
        print("Mean value of sigma: %f" % np.mean(np.sqrt(1 / beta_i)))
        return P, 1 / np.sqrt(2 * beta_i)

