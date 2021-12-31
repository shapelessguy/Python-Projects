folder = ''
from Preprocessing import *
from Modeling import *
physical_devices = tf.config.list_physical_devices('GPU')
tf.config.experimental.set_memory_growth(physical_devices[0], enable=True)
tf.compat.v1.GPUOptions(per_process_gpu_memory_fraction=0.9)

norm_data = pd.read_csv(folder+'datasets/normalized_data.csv', sep=';')
flux_tensor, proc_metadata = loadLocal(folder+'datasets/flux.csv')
spline_tensor = pushMasked(flux_tensor, mask_val=-10.)
#spline_tensor = flux_tensor
metadata = retrieveMetadata(proc_metadata)
reduced_data = pd.read_csv(folder+'datasets/reduced_data.csv', sep=';')
reduced_metadata = retrieveReducedMetadata(reduced_data, metadata)
input_tensor, residuals, n_cutted_series = create_tensor(reduced_data, lenght=72, mask_val=-10.)
n_bands = len(np.unique(reduced_data['passband'].values))

target = reduced_data['target'].values
meta = reduced_metadata.drop(['distmod', 'target'], axis=1)
meta_comp = metadata.drop(['distmod', 'target'], axis=1)

data_encoder = k_data(X=input_tensor, dT=input_tensor[:,:,1], Y=input_tensor[:,:,0])




def custom_mse(mask_value):
    def loss(y_true, y_pred):
        # calculating squared difference between target and predicted values
        loss_ = keras.backend.square(y_pred - y_true)
        # multiplying the values with weights along batch dimension
        loss_ = loss_ * tf.cast((y_true != mask_value), tf.float32)
        # summing both loss values along batch dimension
        loss_ = keras.backend.mean(loss_, axis = 1)
        return loss_
    return loss

params = {'batch_size': 32, 'eval_batch':1, 'epochs': 30, 'verbose': None, 'validation_split': 0.2,
          'n_bottleneck': 20, 'loss': custom_mse(mask_value=-10.)}
auto_enc, enc = runDeepModel(data_encoder, fold=folder, name='LSTM - AutoEncoder', params=params,
                             force_train=False, show_plots=False)[0]

cnn_input = encodeData(enc, input_tensor, metadata=meta.values, target=reduced_metadata['target'].values,
                       n_bands=n_bands, name='complete+')
exotic_input = encodeData(None, spline_tensor, metadata=meta_comp.values, target=metadata['target'].values,
                          n_bands=flux_tensor.shape[1], name='complete++')

pref_features = ['hostgal_specz', 'hostgal_photoz', 'mwebv', 'mean', 'std']
cnn_input_redmeta = encodeData(enc, input_tensor, metadata=meta[pref_features].values,
                               target=reduced_metadata['target'].values, n_bands=n_bands,
                               name='reduced_redmeta')
exotic_input_redmeta = encodeData(None, spline_tensor, metadata=meta_comp[pref_features].values,
                                  target=metadata['target'].values, n_bands=flux_tensor.shape[1],
                                  name='splines_redmeta')
freq = getFreq(reduced_metadata, 'target')


def mywloss(weights):
    def loss(y_true, y_pred):
        yc = tf.clip_by_value(y_pred, 1e-15, 1 - 1e-15)
        loss_ = -(tf.reduce_mean(tf.reduce_mean(y_true * tf.math.log(yc), axis=0) / weights))
        return loss_

    return loss



params = {'batch_size': 16, 'eval_batch': 28, 'epochs': 30, 'verbose': 1, 'earlyS': 3,
          'validation_split': 0.2, 'loss': mywloss(freq), 'mask_value': -10.}

params['f_filter'] = 1
params['f_kernel'] = 1
params['s_kernel'] = 1
params['t_kernel'] = 1
params['f_drop'] = 1
params['s_filter'] = 1
params['f_dense'] = 1
params['s_drop'] = 1
params['t_filter'] = 1

exotic, loss, n = runDeepModel(input, fold=folder, name='CNN - joined', params=params, save_model=False,
                                        force_train=True, show_plots=False)

#randomSearch(exotic_input, folder=folder, name='CNN - joined', params=params, n_iter=150)
#randomSearch(cnn_input, folder=folder, name='CNN - joined', params=params, n_iter=150)
#randomSearch(exotic_input_redmeta, folder=folder, name='CNN - joined', params=params, n_iter=150)
#randomSearch(cnn_input_redmeta, folder=folder, name='CNN - joined', params=params, n_iter=200)
#randomSearch(exotic_input, folder=folder, name='Exotic', params=params, n_iter=50)
#randomSearch(cnn_input, folder=folder, name='Exotic', params=params, n_iter=50)
#randomSearch(exotic_input_redmeta, folder=folder, name='Exotic', params=params, n_iter=150)
#randomSearch(cnn_input_redmeta, folder=folder, name='Exotic', params=params, n_iter=150)



