import pandas as pd

def createUsers():
    dict = {}

    list_df = []                                                               # Dataset identità prelevate dal web
    list_df.append(pd.read_csv('C://Users//Claudio//Desktop//us-500.csv'))       #Carico dataset USA
    list_df.append(pd.read_csv('C://Users//Claudio//Desktop//au-500.csv'))       #Carico dataset Australia
    list_df.append(pd.read_csv('C://Users//Claudio//Desktop//ca-500.csv'))       #Carico dataset Canada
    list_df.append(pd.read_csv('C://Users//Claudio//Desktop//uk-500.csv'))       #Carico dataset Inghilterra
    not_considered = ['county', 'province', 'web', 'company_name']              # attributi non considerati

    for i in range(len(list_df)):                                               # Creo un dataset omogeneo
        for col in list_df[i]:
            if not not_considered.__contains__(col):
                name = col
                if col == 'zip' or col == 'post' or col == 'postal':            # codice postale in tutte le salse
                    name = 'postal'
                if dict.keys().__contains__(name):
                    dict[name] += list_df[i][col].to_list()
                else:
                    dict[name] = list_df[i][col].to_list()

    for i in range(500): dict['state'].append('Canada')                         # Fill dei campi 'state' altrimenti NULL
    for i in range(500): dict['state'].append('United Kingdom')

    def cleanNumber(number):                                                    # Check sui numeri telefonici:
        new_number = ''                                                         # forzatura ad interi
        for char in number:
            if char.isdigit():
                new_number = new_number + char
        if len(new_number) < 5:
            return 'NULL'                                                       #.. al limite NULL
        else:
            return new_number

    for i in range(2000):
        dict['phone1'][i] = cleanNumber(dict['phone1'][i])                      # Esegui funzioni pulizia
        dict['phone2'][i] = cleanNumber(dict['phone2'][i])
        dict['postal'][i] = str(dict['postal'][i])


    df = pd.DataFrame(dict)                                                     # Creazione del dataframe
    df = df.sample(frac=1, axis=1).reset_index(drop=True)
    pd.set_option('display.max_columns', 10)
    pd.set_option('display.max_rows', 20)
    pd.set_option('display.width', 600)

    return dict