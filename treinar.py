import json
import os

import numpy as np

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, callbacks
from sklearn.model_selection import train_test_split

JANELA = 80
EIXOS = 3
CLASSES = ['direita', 'esquerda', 'repouso']
DATASET = 'dataset.json'
SAIDA = 'modelo_tfjs'
KERAS_H5 = 'modelo_keras.h5'


def carregar_dados():
    with open(DATASET) as f:
        raw = json.load(f)

    dados = [d for d in raw if len(d['features']) == JANELA]
    print(f'Amostras: {len(dados)}/{len(raw)}')

    X = np.array([d['features'] for d in dados], dtype=np.float32)
    mapa = {c: i for i, c in enumerate(CLASSES)}
    y = np.array([mapa[d['label']] for d in dados])

    for c in CLASSES:
        print(f'  {c}: {np.sum(y == mapa[c])}')

    return X, y


def deltas(X):
    return X - X[:, 0:1, :]


def gerar_repouso_sintetico(X_gestos, n_amostras):
    rng = np.random.default_rng(42)
    permutacoes = [[1, 0, 2], [2, 1, 0], [0, 2, 1], [1, 2, 0], [2, 0, 1]]
    sinteticas = []
    for _ in range(n_amostras):
        i = rng.integers(0, len(X_gestos))
        perm = permutacoes[rng.integers(0, len(permutacoes))]
        x = X_gestos[i][:, perm].copy()
        sinteticas.append(x)
    return np.array(sinteticas, dtype=np.float32)


def time_shift(X, y, fator=2):
    rng = np.random.default_rng(42)
    aug_X, aug_y = [X], [y]
    for _ in range(fator):
        X_a = X.copy()
        for i in range(len(X_a)):
            shift = rng.integers(-5, 6)
            if shift != 0:
                X_a[i] = np.roll(X_a[i], shift, axis=0)
        aug_X.append(X_a.astype(np.float32))
        aug_y.append(y)
    return np.concatenate(aug_X), np.concatenate(aug_y)


def preparar_treino(X, y):
    X_d = deltas(X)
    idx_gestos = (y == 0) | (y == 1)
    X_gestos = X_d[idx_gestos]
    n_sinteticas = len(X_gestos)
    X_sint = gerar_repouso_sintetico(X_gestos, n_sinteticas)
    y_sint = np.full(len(X_sint), 2, dtype=y.dtype)
    print(f'Repouso sintetico (axis-swap): +{len(X_sint)} amostras')

    X_full = np.concatenate([X_d, X_sint])
    y_full = np.concatenate([y, y_sint])
    return X_full, y_full


def criar_modelo():
    return keras.Sequential([
        layers.Input(shape=(JANELA, EIXOS)),
        layers.Conv1D(32, 5, activation='relu'),
        layers.MaxPooling1D(2),
        layers.Conv1D(64, 3, activation='relu'),
        layers.GlobalAveragePooling1D(),
        layers.Dropout(0.3),
        layers.Dense(32, activation='relu'),
        layers.Dense(len(CLASSES), activation='softmax')
    ])


def treinar(X_train, y_train, X_val, y_val):
    X_train, y_train_idx = time_shift(X_train, np.argmax(y_train, axis=1), fator=2)
    y_train = keras.utils.to_categorical(y_train_idx, len(CLASSES))
    print(f'Treino apos time-shift: {len(X_train)}')

    modelo = criar_modelo()
    modelo.compile(
        optimizer=keras.optimizers.Adam(0.001),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    cb = [
        callbacks.EarlyStopping(monitor='val_accuracy', patience=20, restore_best_weights=True, verbose=1),
        callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=8, min_lr=1e-5, verbose=1)
    ]

    modelo.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=200,
        batch_size=32,
        callbacks=cb,
        verbose=1
    )
    return modelo


def avaliar(modelo, X_val, y_val):
    loss, acc = modelo.evaluate(X_val, y_val, verbose=0)
    print(f'\nVal: acc={acc * 100:.1f}% loss={loss:.4f}\n')

    y_pred = np.argmax(modelo.predict(X_val, verbose=0), axis=1)
    y_true = np.argmax(y_val, axis=1)
    print(f'{"":>10} {"DIR":>6} {"ESQ":>6} {"REP":>6}')
    for i, c in enumerate(CLASSES):
        linha = [int(np.sum((y_true == i) & (y_pred == j))) for j in range(len(CLASSES))]
        print(f'{c:>10} {linha[0]:>6} {linha[1]:>6} {linha[2]:>6}')


def limpar_layer(layer):
    config = dict(layer['config'])
    for f in ['module', 'registered_name', 'optional', 'sparse', 'ragged',
              'build_config', 'compile_config', 'synchronized',
              'quantization_config', 'keepdims', 'autocast']:
        config.pop(f, None)
    if isinstance(config.get('dtype'), dict):
        d = config['dtype']
        if d.get('class_name') == 'DTypePolicy':
            config['dtype'] = d['config']['name']
        elif 'name' in d:
            config['dtype'] = d['name']
        else:
            config['dtype'] = 'float32'
    for key, v in list(config.items()):
        if isinstance(v, dict) and v.get('class_name') and 'config' in v:
            limpo = dict(v)
            limpo.pop('module', None)
            limpo.pop('registered_name', None)
            config[key] = limpo
    return {'class_name': layer['class_name'], 'config': config}


def topologia_tfjs(modelo):
    keras_json = json.loads(modelo.to_json())
    config = keras_json['config']
    layers_in = list(config['layers'])

    input_layer = None
    if layers_in and layers_in[0]['class_name'] == 'InputLayer':
        input_layer = layers_in.pop(0)

    layers_out = []
    for i, layer in enumerate(layers_in):
        novo = limpar_layer(layer)
        if i == 0 and input_layer is not None:
            shape = input_layer['config'].get('batch_shape') or input_layer['config'].get('batch_input_shape')
            novo['config']['batch_input_shape'] = list(shape)
        layers_out.append(novo)

    return {
        'class_name': keras_json['class_name'],
        'config': {'name': config.get('name', 'sequential'), 'layers': layers_out}
    }


def exportar_tfjs(modelo, dir_saida):
    os.makedirs(dir_saida, exist_ok=True)

    weight_specs, binarios = [], []
    for camada in modelo.layers:
        for var, arr in zip(camada.weights, camada.get_weights()):
            nome_curto = var.name.split(':')[0]
            nome = nome_curto if '/' in nome_curto else camada.name + '/' + nome_curto
            weight_specs.append({'name': nome, 'shape': list(arr.shape), 'dtype': 'float32'})
            binarios.append(arr.astype(np.float32).tobytes())

    with open(os.path.join(dir_saida, 'weights.bin'), 'wb') as f:
        for b in binarios:
            f.write(b)

    manifest = {
        'format': 'layers-model',
        'generatedBy': 'keras v' + keras.__version__,
        'convertedBy': 'treinar.py',
        'modelTopology': {
            'keras_version': '2.11.0',
            'backend': 'tensorflow',
            'model_config': topologia_tfjs(modelo)
        },
        'weightsManifest': [{'paths': ['weights.bin'], 'weights': weight_specs}]
    }

    with open(os.path.join(dir_saida, 'model.json'), 'w') as f:
        json.dump(manifest, f)


def main():
    X, y = carregar_dados()
    X_full, y_full = preparar_treino(X, y)

    X_train, X_val, y_train_idx, y_val_idx = train_test_split(
        X_full, y_full, test_size=0.2, random_state=42, stratify=y_full
    )
    y_train = keras.utils.to_categorical(y_train_idx, len(CLASSES))
    y_val = keras.utils.to_categorical(y_val_idx, len(CLASSES))

    modelo = treinar(X_train, y_train, X_val, y_val)
    avaliar(modelo, X_val, y_val)

    modelo.save(KERAS_H5)
    print(f'\nKeras: {KERAS_H5}')

    exportar_tfjs(modelo, SAIDA)
    print(f'TFJS: {SAIDA}/')

    print('\nDeploy:')
    print(f'  scp -i C:/Users/Thiago/Downloads/ssh-key-2026-03-20.key {SAIDA}/model.json {SAIDA}/weights.bin ubuntu@152.67.46.103:/tmp/')
    print('  ssh ... "sudo mv /tmp/model.json /tmp/weights.bin /opt/kinetix-relay/public/modelo/"')


if __name__ == '__main__':
    main()
