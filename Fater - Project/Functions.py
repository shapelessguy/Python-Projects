import numpy as np
import seaborn as sn
import statsmodels.api as sm
import statsmodels
import pandas as pd
from matplotlib import pyplot as plt
from pandas import Series
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.arima_model import ARIMA
from pandas.plotting import register_matplotlib_converters
from datetime import timedelta
import random
import math

hist_series_tampons = pd.DataFrame()
sell_out = pd.DataFrame()
tampax_GRPs = pd.DataFrame()
promo = pd.DataFrame()

datasets = {}
def generateNoisedSellIn(noise=1, seed=0):
    global hist_series_tampons
    global datasets
    if (noise, seed) in datasets: return datasets[(noise, seed)]
    newDataset = hist_series_tampons.copy()
    if noise != 0:
        newDataset['Data Rif'] = newDataset.apply(lambda x: x['Data Rif'] + timedelta(days=random.randrange(-noise, noise*noise)), axis=1)
    datasets[(noise, seed)] = newDataset
    return newDataset

def range_to_ts(df, begin='Inizio', end='Fine'):
    ''' Take a dataframe with a 'beginning' and 'end' columns and returns
        a dataframe with a row for each day of promotion '''
    days = df.apply(lambda x: pd.date_range(start=x[begin], end=x[end]), axis=1)
    data = []
    for i, promo_range in enumerate(days):
        for day in promo_range:
            data.append([day, df['Customer'][i], df['Segment'][i], 1])
    promo = pd.DataFrame(data, columns=['Data Rif', 'Customers', 'Segment', 'Promo'])
    return promo

def initializeDatasets():
    register_matplotlib_converters()
    dataset_content_new_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/Dataset%20Content%20NEW.csv?alt=media&token=5ea83efc-fa40-4591-ae66-6c91cd3f3548'
    hist_series_tamp_new_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/historical_series_tampons_NEW.csv?alt=media&token=8d6b610f-afac-4fea-8d2e-4d91f197de3e'
    list_inc_mont_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/list_increase_monthly.csv?alt=media&token=150e1733-a224-4c97-a6a5-0b9fe26b1a1a'
    tampax_grp_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/tampax_GRPs.csv?alt=media&token=a875ec17-6efd-40bd-abd9-24d6d6361903'
    tamp_hist_promo_new_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/tampons_historical_promo_NEW.csv?alt=media&token=b1e81be1-2e0a-4d59-a4a2-d47a49208365'
    tamp_promo_plan_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/tampons_promo_planning_NEW.csv?alt=media&token=99fb2b9a-a5f5-4861-8adf-5e342da89a97'
    volumes_sell_out_tamp_url = 'https://firebasestorage.googleapis.com/v0/b/moneyguard-1565995930582.appspot.com/o/volumes_sell_out_tampons.csv?alt=media&token=f93bee88-129d-4f06-931c-2681925000c6'

    np.seterr(divide='ignore')
    global hist_series_tampons
    global sell_out
    global tampax_GRPs
    global promo

    hist_series_tampons = pd.read_csv(hist_series_tamp_new_url, sep='\t', decimal=",")
    sell_out = pd.read_csv(volumes_sell_out_tamp_url, sep=';', decimal=",")
    tampax_GRPs = pd.read_csv(tampax_grp_url, sep=';', decimal=",")
    promo = pd.read_csv(tamp_hist_promo_new_url, sep=';', decimal=",")
    sell_out['week'] = pd.to_datetime(sell_out['week'], format='W %d/%m/%y')
    #tampax_GRPs['Week'] = tampax_GRPs.apply(lambda x: x['Week'][:3]+x['Week'][3].upper()+x['Week'][4:], axis=1)
    toInteger = {'gen':'01', 'feb':'02', 'mar':'03', 'apr':'04', 'mag':'05', 'giu':'06', 'lug':'07', 'ago':'08',
                 'set':'09', 'ott':'10', 'nov':'11', 'dic':'12'}
    tampax_GRPs['Week'] = tampax_GRPs.apply(lambda x: x['Week'][:3] + toInteger[x['Week'][3:6]] + x['Week'][6:], axis=1)
    tampax_GRPs['Week'] = pd.to_datetime(tampax_GRPs['Week'], format='%d-%m-%y')
    promo['Inizio Promo'] = pd.to_datetime(promo['Inizio Promo'], format='%d/%m/%Y')
    promo['Fine Promo'] = pd.to_datetime(promo['Fine Promo'], format='%d/%m/%Y')
    hist_series_tampons['Data Rif'] = pd.to_datetime(hist_series_tampons['Data Rif'], format='%d/%m/%y')
    promo = promo.rename(columns={"Inizio Promo": "Inizio", "Fine Promo": "Fine"})
    promo = range_to_ts(promo)
    promo = promo.set_index(['Data Rif', 'Customers', 'Segment'])
    hist_series_tampons = hist_series_tampons.join(promo, on=['Data Rif', 'Customers', 'Segment']).drop_duplicates().fillna(0)

def getSegmentComponents():
    associations = {}
    for index, row in hist_series_tampons.iterrows():
        segment = row['Segment']
        product = row['Products']
        if associations.get(segment, -1) == -1: associations[segment] = []
        if product not in associations[segment]: associations[segment].append(product)
    for list_ in associations.values():
        list_.sort()
    return associations


def filter(dataset=hist_series_tampons, product='', segment='',
             fromData=pd.Timestamp(year=2017, month=1, day=1),
             toData=pd.Timestamp(year=2019, month=1, day=1)):
    '''
    Reconstructs the 'hist_series_tampons' Pandas dataframe.
    Parameters:
        -product:   filters over a specific product
        -segment:   filters over a specific market segment
        -fromData:  initial data for the reconstruction
        -toData:    initial data for the reconstruction
    Returns:
        Indexed Pandas dataframe with just one sum column
    '''
    sea_series = dataset.copy()
    if fromData != None: sea_series = sea_series.loc[sea_series['Data Rif'] > fromData]
    if toData != None: sea_series = sea_series.loc[sea_series['Data Rif'] < toData]
    sea_series = sea_series.set_index('Data Rif')
    if product != '': sea_series = sea_series.loc[sea_series['Products'] == product]
    if segment != '': sea_series = sea_series.loc[sea_series['Segment'] == segment]
    return resample(sea_series, '1D')

def resample(dataset, seasonality='7D'):
    '''
    Reconstructs the input Pandas dataframe.
    Parameters:
        -seasonality:   specifies the aggregation data interval (1D, 2D, etc.)
    Returns:
        Indexed Pandas dataframe (according to the aggregation) with just one sum column
    '''
    period = 1
    if 'D' in seasonality and len(seasonality)>1: period = int(seasonality.replace('D',''))
    output = dataset.resample(seasonality).sum()
    return output


def getSeries_perProduct(dataset=hist_series_tampons, diff_periods=0, seasonality='7D',
                        log=False, minimumSeriesSize=0, norm=False,
                        fromData=pd.Timestamp(year=2017, month=1, day=1),
                        toData=pd.Timestamp(year=2019, month=1, day=1)):
    '''
    Returns a new Pandas dataframe base on the 'hist_series_tampons' dataframe
    which contains a subset of time series specified by the user.
    Parameters:
        -diff_periods:  int
            differentiation with a specified lag number of all time series
        -seasonality:   string
            specifies the aggregation data interval (W-SUN, D, etc.)
        -log:           bool
            applies logaritmic transformation to the series
        -minimumSeriesSize: int
            filters over the minimum number of elements in a series
        -norm:          bool
            applies normal transformation to the series
        -fromData:      datetime64 dtype
            initial data for reconstruction
        -toData:        datetime64 dtype
            final date for reconstruction
    Returns:
        Indexed Pandas dataframe (according to the aggregation), with that many columns
        as they have been generated. This dataframe will be later referred as a 'bag'.
    '''
    toReturn = {}
    promos = []
    for i in range(22):
        text = 'Product {}'.format(i + 1)
        series = filter(dataset=dataset, product=text, fromData=fromData, toData=toData)
        if len(series.columns)>1:
            promos.append(series.take([1], axis=1).rename(columns={"Promo": text}))
        series = series.take([0], axis=1)
        if len(series) <= 1: continue
        if diff_periods != 0: series = series.diff(diff_periods)
        if log: series['Standard Units'] = np.log(series['Standard Units'])
        toReturn[text] = series
    bag_series = concatenateSeries(toReturn, minimumSeriesSize=minimumSeriesSize)
    promos = pd.concat(promos).fillna(0).sum(axis=1)
    bag_series['Overall'] = bag_series.sum(axis=1)
    bag_series['Promo'] = promos.take([-1], axis=1)

    bag_series = resample(bag_series, seasonality)
    #for index in range(len(bag_series)):
    #   for col in bag_series.columns:
    #        bag_series[col][index] = index
    #print(bag_series)
    mean = {col:bag_series[col].mean() for col in bag_series.columns}
    std = {col:bag_series[col].std() for col in bag_series.columns}
    if norm:
        for col in bag_series.columns:
            bag_series[col] = (bag_series[col] - mean[col]) / std[col]
    return bag_series, mean, std


def concatenateSeries(series_dict, minimumSeriesSize=0):
    '''
    Concatenates the different time series in the dictionary 'series_dict'
    if they have a specified minimum number of elements.
    Returns:
        Pandas dataframe.
    '''
    listSeries = []
    for key, value in series_dict.items():
        value.columns = [key, ]
        if len(value) > minimumSeriesSize: listSeries.append(value)
    if len(listSeries) == 0: return None
    df = pd.concat(listSeries, axis=1).fillna(0)
    return df


def PlotACFs(pdSeries_bag, partial=False, lags=10):
    '''
    Plots over a grid (whose dimensions are related to the 'pdSeries_bag')
    the AFC or partialAFC plots.
    Parameters:
        -pdSeries_bag:  bag dataframe used
        -partial:       specifies if the partialAFC has to be plotted
                        (default is full)
        -lags:          specifies the maximum lag to be plotted
    '''
    n = len(pdSeries_bag.columns)
    dim = (n // 2 + n % 2, 2)
    if dim[0] == 1: dim = 2, dim[1]
    figsize = (20, dim[0] * 5)
    fig, ax = plt.subplots(dim[0], dim[1], figsize=figsize)
    for i in range(n):
        text = pdSeries_bag.columns[i]
        if text == 'Overall': continue
        series = pdSeries_bag[text]
        axis = ax[i // dim[1]][i - i // dim[1] * dim[1]]
        if partial:
            sm.graphics.tsa.plot_pacf(series, lags=lags, ax=axis, title=text)
        else:
            sm.graphics.tsa.plot_acf(series, lags=lags, ax=axis, title=text)
    series = pdSeries_bag['Overall']
    axis = ax[dim[0] - 1][dim[1] - 1]
    if partial:
        sm.graphics.tsa.plot_pacf(series, lags=lags, ax=axis, title='Overall')
    else:
        sm.graphics.tsa.plot_acf(series, lags=lags, ax=axis, title='Overall')


def plotColumns(pdSeries_bag, RMean=False, RstdDeviation=False):
    '''
    Plots over a grid (whose dimensions are related to the 'pdSeries_bag')
    the plot that describes the time series in the bag.
    Parameters:
        -pdSeries_bag:  bag dataframe used
        -RMean:         specifies if the moving average has to be plotted
        -RstdDeviation: specifies if the moving std_dev has to be plotted
    '''
    n = len(pdSeries_bag.columns)
    figsize = (10, 5)
    if n == 1:
        fig, ax = plt.subplots(1, figsize=figsize)
        if 'Overall' in pdSeries_bag.columns:
            Plot(ax, pdSeries_bag['Overall'], color='green', title='Overall', RMean=RMean, RstdDeviation=RstdDeviation)
    else:
        dim = (n // 2 + n % 2, 2)
        if dim[0] == 1: dim = 2, dim[1]
        fig, ax = plt.subplots(dim[0], dim[1], figsize=figsize)
        for i in range(n):
            text = pdSeries_bag.columns[i]
            if text == 'Overall': continue
            series = pdSeries_bag[text]
            axis = ax[i // dim[1]][i - i // dim[1] * dim[1]]
            Plot(axis, series, title=text, RMean=RMean, RstdDeviation=RstdDeviation)
        if 'Overall' in pdSeries_bag.columns:
            series = pdSeries_bag['Overall']
            axis = ax[dim[0] - 1][dim[1] - 1]
            Plot(axis, series, color='green', title='Overall', RMean=RMean, RstdDeviation=RstdDeviation)
    plt.show()


def Plot(axis, series, title, color='blue', RMean=False, RstdDeviation=False):
    '''
    Plots over one axis a time series.
    Parameters:
        -axis:          specifies the axis (as a pyplot object)
        -series:        soecifies the time series
        -title:         specifies the title of the plot
        -color:         specifies the color of the main trend
        -RMean:         specifies if the moving average has to be plotted
        -RstdDeviation: specifies if the moving std_dev has to be plotted
    '''
    rolling_mean = series.rolling(window=12).mean()
    rolling_std = series.rolling(window=12).std()
    axis.set_title(title)
    axis.plot(series, color=color, label='Original')
    if RMean: axis.plot(rolling_mean, color='red', label='Rolling Mean')
    if RstdDeviation: axis.plot(rolling_std, color='black', label='Rolling Std')
    axis.legend(loc='best')


def showCorrelations(pdSeries):
    '''
    Plots over a grid the correlation between the differnt time series
    in the bag dataframe 'pdSeries'.
    '''
    plt.subplots(1, 1, figsize=(12, 9))
    sn.heatmap(pdSeries.corr(), annot=True)
    plt.show()


def segmentAggregate(pdSeries, norm=False):
    '''
    Aggregates the columns in the bag dataframe 'pdSeries' according to the market segments.
    Note that the bag dataframe needs to be aggregated previously according to the products.
    Returns:
        bag dataframe aggregated by segments
    '''
    series = pdSeries.copy()
    associations = getSegmentComponents()
    for key in associations:
        list_associations = []
        for el in associations[key]:
            if el in series.columns: list_associations.append(el)
        series[key] = series.loc[:, list_associations].sum(axis=1)
        series = series.drop(columns=list_associations)
    overall = series.loc[:, 'Overall']
    series = series.drop(columns=['Overall'])
    series['Overall'] = overall
    series = series.fillna(0)
    mean = {col:series[col].mean() for col in series.columns}
    std = {col:series[col].std() for col in series.columns}
    colsToDrop = []
    if norm:
        for col in series.columns:
            if mean[col] == 0 and std[col] == 0: colsToDrop.append(col)
            else: series[col] = (series[col] - mean[col]) / std[col]
    series = series.drop(columns=colsToDrop)
    return series, mean, std


def KPSS_test(series_bag):
    '''
        Executes a KPSS test over all the time series in the bag dataframe and prints the results
    '''
    print(' --> Null hypothesis: stationary')
    for column in series_bag.columns:
        stats = statsmodels.tsa.stattools.kpss(series_bag[column], lags='legacy', regression='c')
        print('Series', column, 'test-statistic: {:.2f}'.format(stats[0]),
              'p-value: {:.2f}'.format(stats[1]), 'Critical values: ', stats[3])


def getMSE(results, series, winSize):
    '''
    Computes the MSE of the predictions as the MSE computed over a window specified by 'winSize'.
    Parameters:
        -results:   predicted time series
        -series:    time series to predict
        -winSize:   window size (expressed as the number of ticks of the series)
    '''
    try:
        prediction = results.predict(1, len(series) - 1, typ='levels')
    except:
        prediction = results.predict(1, len(series) - 1)
    df = pd.DataFrame(prediction.iloc[len(prediction) - winSize:])
    df[1] = series.iloc[len(series) - winSize:]
    df['MSE'] = np.power(df[0] - df[1], 2)
    return np.sum(df['MSE']) / winSize


def computeARIMA(series, ticks, order=None):
    '''
    Fits the time series 'series' using the ARIMA model and returns the predicted
    time series, its MSE and the (p,d,q) parameters used by the model.
    Parameters:
        -series:    time series to predict
        -ticks:     window size (expressed as the number of ticks of the series)
        -order:     (p,d,q) tuple, where p, d and q are the parameters for the AR,
                    I and MA procedure. Note that if no order is specified, the method
                    iteratively looks for the best parameters that minimizes the MSE.
    Returns:
        (statsmodels.tsa.arima_model.ARMAResultsWrapper, float, tuple)
    '''
    ticks_toPredict = ticks
    train_series = series[:-ticks_toPredict]
    if order == None:
        order = (0, 1, 0)
        mse_min = 999999999
        for p in range(0, 10):
            for d in range(1, 2):
                for q in range(0, 5):
                    try:
                        model = ARIMA(train_series, order=(p, d, q))
                        results = model.fit(disp=-1)
                        mse = getMSE(results, series, winSize=ticks_toPredict)
                        if mse < mse_min:
                            mse_min = mse
                            order = (p, d, q)
                    except:
                        None
    try:
        model = ARIMA(train_series, order)
        results = model.fit(disp=-1)
        mse = getMSE(results, series, winSize=ticks_toPredict)
    except np.linalg.LinAlgError as e:
        return 'SVD did not converge', None, None
    except ValueError as ve:
        return 'Bad coefficient choice', None, None
    return results, float(mse), order


def plotARIMA(results, ax, mse, lenght, title=''):
    '''
    Plots over one axis the plot of the time series generated by the ARIMA method.
    Parameters:
        -results:   time series predicted by the model
        -ax:        specifies the axis (as a pyplot object)
        -mse:       prediction related MSE
        -lenght:    total lenght of the series to be predicted
        -title:     plot title
    '''
    if type(results) == str:
        title = results
    else:
        results.plot_predict(1, lenght, ax=ax)
    if type(mse) == float: title += str(" - MSE: {:.1f} Fater's MSE").format(mse / 100000)
    ax.set_title(title)


def ARIMA_model(pdSeries_bag, ticks, order={}):
    '''
    Fits the ARIMA model over all the series in the bag dataframe 'pdSeries_bag', and then
    it representsthe results over a grid whose dimensions are dinamically computed.
    Parameters:
        -pdSeries_bag:  bag dataframe of time series to predict
        -ticks:         window size (expressed as the number of ticks of the series)
        -order:         dictionary of (p,d,q) tuples, where p, d and q are the parameters for the AR,
                        I and MA procedure. Note that if no order is specified, the method
                        iteratively looks for the best parameters that minimizes the MSE.
    '''
    print('Fitting ARIMA Model')
    n = len(pdSeries_bag.columns)
    dim = (n // 2 + n % 2, 2)
    if dim[0] == 1: dim = 2, dim[1]
    figsize = (20, dim[0] * 5)
    fig, ax = plt.subplots(nrows=dim[0], ncols=dim[1], figsize=figsize)
    output = {}
    for i in range(n):
        text = pdSeries_bag.columns[i]
        if text == 'Overall': continue
        series = pdSeries_bag.filter([text])
        axis = ax[i // dim[1]][i - i // dim[1] * dim[1]]
        order_i = order.get(text, None)
        results, mse, order_computed = computeARIMA(series, ticks=ticks, order=order_i)
        if order_i is None: print(' --> ARIMA on {} series computed. Best parameters: {}'.format(text, order_computed))
        plotARIMA(results, axis, title=text, mse=mse, lenght=len(series))
        output[text] = (order_computed, mse, len(series))
    if 'Overall' in pdSeries_bag.columns:
        order_i = order.get('Overall', None)
        series = pdSeries_bag['Overall']
        axis = ax[dim[0] - 1][dim[1] - 1]
        results, mse, order_computed = computeARIMA(series, ticks=ticks, order=order_i)
        if order is None: print(' --> ARIMA on Overall series computed. Best parameters: {}'.format(order_computed))
        plotARIMA(results, axis, lenght=len(series), title='Overall', mse=mse)
        output['Overall'] = (order_computed, mse, len(series))
    plt.show()
    return output

def conversion(input):
    intervals = [(0, 0)]
    for el in np.linspace(0, 1, 8):
        intervals.append((intervals[-1][-1], el))
    intervals = intervals[2:]
    dictionary = {'{}D'.format(i + 1): intervals[i] for i in range(len(intervals))}
    if type(input)==str:
        return dictionary[input][0]
    else:
        for key, value in dictionary.items():
            if input>=value[0] and input <value[1]:
                return key
        return '7D'

def normalizeDataset(dataset, mean=None, std=None):
    output = pd.DataFrame()
    if mean is None and std is None:
        mean = {col: dataset[col].mean() for col in dataset.columns}
        std = {col: dataset[col].std() for col in dataset.columns}
        colsToDrop = []
        for col in dataset.columns:
            if mean[col] == 0 and std[col] == 0:
                colsToDrop.append(col)
            else:
                output[col] = (dataset[col] - mean[col]) / std[col]
        output = output.drop(columns=colsToDrop)
        return output, mean, std
    else:
        for col in dataset.columns:
            output[col] = dataset[col] * std[col] + mean[col]
        return (output, )