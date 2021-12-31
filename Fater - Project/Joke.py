def initialize():
  import pandas as pd
  from matplotlib import pyplot as plt
  url1 = '/content/drive/My Drive/Projects/Fater Challenge/Fater_data/historical_series_tampons_NEW.csv'
  hist_series_tampons = pd.read_csv(url1, sep='\t', decimal=",")
  hist_series_tampons['Data Rif'] = pd.to_datetime(hist_series_tampons['Data Rif'])

class graphOptions:
  def __init__(self, dataframe, xName, yName, title, stopAt=None, productName = ''):
    self.productName = productName
    if productName!='': self.dataframe = dataframe[dataframe.Products.eq(productName)]
    else: self.dataframe = dataframe
    self.xName = xName
    self.yName = yName
    self.title = title
    self.stopAt = stopAt

def aggregateIntervals(fullx, fully, aggregate):
  day_toNs = 10**9*60*60*24
  minX = min(fullx)
  x = [pd.Timestamp(((n.value-minX.value)//(day_toNs*aggregate))*(day_toNs*aggregate)+minX.value) for n in fullx]
  points = {}
  for key,value in zip(x,fully):
      points[key] = points.get(key, 0) + value
  return list(points.keys()), list(points.values())

def aggregateEntries(fullx, fully, aggregate):
  x = [fullx[n*aggregate] for n in range(0, int(len(fullx)/aggregate))]
  y = [sum(fully[n*aggregate:(n+1)*aggregate]) for n in range(0, int(len(fully)/aggregate))]
  return x,y

def indexAt(x, timestamp):
  if timestamp==None: return len(x)
  maxIndex = 0
  for i in range(len(x)):
    if x[i].value > timestamp.value:
      break
    maxIndex+=1
  return maxIndex

#TimeInterval aggregation (aggregateEntry: number of units aggregated in one, aggregateInterval: units aggregated over certain time periods (days))
def plotTimeValue(options, aggregateEntry = 1, aggregateInterval = 1):
  plt.figure(figsize=(15,10))
  x, y = [i for i in zip(*sorted(zip(options.dataframe[options.xName], options.dataframe[options.yName])))]
  x, y = x[:indexAt(x, options.stopAt)], y[:indexAt(x, options.stopAt)]
  x, y = aggregateEntries(x, y, aggregateEntry)
  x, y = aggregateIntervals(x, y, aggregateInterval)
  plt.plot(x, y)
  info = options.title
  if op.productName != '': info += " - {}".format(op.productName)
  if aggregateInterval != 1: info += " - aggregation by intervals: {} days".format(aggregateInterval)
  if aggregateEntry != 1: info += " - aggregation by entries: {}".format(aggregateEntry)
  plt.title(info)
  plt.show()

initialize()

op = graphOptions(dataframe = hist_series_tampons,
                  xName = 'Data Rif',
                  yName = 'Standard Units',
                  title = 'Standard units sales series',
                  stopAt = pd.Timestamp(year=2019, month=4, day=1),
                  productName = 'Product 8'
                  )
plotTimeValue(op, aggregateEntry = 1, aggregateInterval = 7)