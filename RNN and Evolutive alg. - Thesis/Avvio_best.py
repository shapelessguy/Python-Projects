import Dataset as ds

ind=[0.29436010404045576, 0.9650182949121683, 1, 0.6373361976113011, 0.6280896514234442, 0.07919296048752689, 0.13116260516929334]

def Decodifica_ind(ind):
    lr = 0.001+(float)(ind[0])*0.009
    DimRetSeqLayers = (int)(1+ind[1]*40)
    DimNORetSeqLayers = (int)(1+ind[2]*40)
    dropout1 = ind[3]*0.8
    dropout2 = ind[3]*0.8
    Params = (int)(1 + ind[5]*4)
    #activation = Decodifica(ind[6])
    return lr, DimRetSeqLayers, DimNORetSeqLayers, dropout1, dropout2, Params

lr, DimRetSeqLayers, DimNORetSeqLayers, dropout1, dropout2, Params = Decodifica_ind(ind=ind)
lr, DimRetSeqLayers, DimNORetSeqLayers, dropout1, dropout2, Params = 0.006, 150, 150, 0.5, 0.5, 1

epochs = 150 #Epoche rete neurale
B_size = 2048
perc_ev = 100
string_save=''

train, y_train, test, y_test = ds.CreateDataset(perc_ev, listFiles = ['FlatTree_VBFH3000_spin0.root', 'FlatTree_ggFH3000_spin0.root'])
#trainno, y_trainno, test, y_test = ds.CreateDataset(perc_ev, listFiles = ['FlatTree_VBFH3000_spin0.root', 'FlatTree_ggFH3000_spin0.root'])

train_signal, train_background, test_signal, test_background = ds.Divide_datasets(train, y_train, test, y_test)
ds.run_TrainandTest(
                    train, y_train, test, y_test,
                    train_signal, train_background, test_signal, test_background,
                    epochs=epochs,
                    B_size=B_size,
                    string_save=string_save,
                    lr=lr,
                    DimRetSeqLayers=DimRetSeqLayers,
                    DimNORetSeqLayers=DimNORetSeqLayers,
                    dropout1=dropout1,
                    dropout2=dropout2,
                    Params=Params,
                    verbose=True
                    )
