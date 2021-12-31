import pandas as pd
import urllib.request, urllib.error, urllib.parse

pd.set_option('display.max_columns', 15)
pd.set_option('display.max_rows', 50)
pd.set_option('display.width', 600)

def addNewEntries(df, string):
    df['nuovi_' + string] = df[string]
    act_reg = ''
    act_val = 0
    for row in zip(df['denominazione_regione'].index, df['denominazione_regione'], df[string]):
        reg = row[1]
        val = row[2]
        if reg != act_reg:
            act_reg = reg
            val = 0
            act_val = 0
        else:
            val = int(val) - int(act_val)
            act_val += val
        df['nuovi_' + string][row[0]] = str(val)


def Cleaning(url, finalName, full = False):
	response = urllib.request.urlopen(url)
	webContent = str(response.read())
	lines = webContent.split('\\n')

	dict = {}
	for line in lines:
		line = line.replace(",", "")
		if line.__contains__('"'):
			clean_line = line
			clean_line = clean_line[clean_line.find('"') + 1:]
			clean_line = clean_line[:clean_line.find('"')]
			value = line[line.find(": ") + 2:].replace('"', "").replace("\n", "")
			if dict.get(clean_line, -1) == -1:
				dict[clean_line] = []
			else:
				dict[clean_line].append(value)

	df = pd.DataFrame(dict)
	df = df.sort_values(by=['codice_regione', 'data'])

	if full:
		addNewEntries(df, 'ricoverati_con_sintomi')
		addNewEntries(df, 'terapia_intensiva')
		addNewEntries(df, 'totale_ospedalizzati')
		addNewEntries(df, 'isolamento_domiciliare')
		addNewEntries(df, 'dimessi_guariti')
		addNewEntries(df, 'deceduti')
		addNewEntries(df, 'totale_casi')
		addNewEntries(df, 'tamponi')

	df.to_csv(finalName, index=False)

Cleaning('https://raw.githubusercontent.com/pcm-dpc/COVID-19/master/dati-json/dpc-covid19-ita-regioni.json', "CSVData.csv", True)
Cleaning('https://raw.githubusercontent.com/pcm-dpc/COVID-19/master/dati-json/dpc-covid19-ita-province.json', "CSVDataProvince.csv", False)