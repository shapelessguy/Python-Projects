import pandas as pd

dataset1 = 'C://Users//39339//Desktop//Hospital_.csv'
dataset2 = 'C://Users//39339//Desktop//CSVDataProvince_.csv'

pd.set_option('display.max_columns', 15)
pd.set_option('display.max_rows', 50)
pd.set_option('display.width', 600)

df = pd.read_csv(dataset1, delimiter = ';', encoding = 'utf-8')
df1 = pd.DataFrame()
df1['comune'] = df['Comune']
df1['prov'] = df['Provincia'].str.lower()
df1['regione'] = df['Regione']
df1.to_csv(dataset1.replace('_',''), index=False, header = False)

df = pd.read_csv(dataset2, delimiter = ',', encoding = 'utf-8')
df['denominazione_provincia'] = df['denominazione_provincia'].str.lower()
df['denominazione_provincia'] = df['denominazione_provincia'].replace('verbano-cusio-ossola','verbania')
df['denominazione_provincia'] = df['denominazione_provincia'].replace("reggio nell\\'emilia",'reggio emilia')
df['denominazione_provincia'] = df['denominazione_provincia'].replace("l\\'aquila","l'aquila")
df['denominazione_provincia'] = df['denominazione_provincia'].replace('barletta-andria-trani','barletta')
df['denominazione_provincia'] = df['denominazione_provincia'].replace('forl\\xc3\\xac-cesena',"forli'")

comuni = []
for string in df['denominazione_provincia']:
    if not string in comuni:
        comuni.append(string)
for string in comuni: print(string)
df.to_csv(dataset2.replace('_',''), index=False, header = False)