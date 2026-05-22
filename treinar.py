import json
import os

import numpy as np

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, callbacks
from sklearn.model_selection import train_test_split

JANELA = 80
CLASSES = ['direita', 'esquerda', 'repouso']
DATASET = 'dataset.json'
SAIDA = 'modelo_tfjs'
KERAS_H5 = 'modelo_keras.h5'


EIXOS = 2


def carregar_dados():
    with open(DATASET) as f:
        raw = json.load(f)

    dados = [d for d in raw if len(d['features']) == JANELA]
    print(f'Amostras validas: {len(dados)}/{len(raw)}')

    mapa = {c: i for i, c in enumerate(CLASSES)}
    X = np.array([d['features'] for d in dados], dtype=np.float32)
    X = X[:, :, :EIXOS]
    y = np.array([mapa[d['label']] for d in dados])

    for c in CLASSES:
        print(f'  {c}: {np.sum(y == mapa[c])}')

    y_cat = keras.utils.to_categorical(y, len(CLASSES))
    return train_test_split(X, y_cat, test_size=0.2, random_state=42, stratify=y)


def deltas(X):
    return X - X[:, 0:1, :]


def matriz_rotacao_2d(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=np.float32)


def augmentar(X, y, fator=4):
    rng = np.random.default_rng(42)
    aug_X, aug_y = [X], [y]
    MAX_ANG = np.deg2rad(20)
    MAX_SHIFT = 4
    for _ in range(fator):
        X_a = X.copy()
        for i in range(len(X_a)):
            R = matriz_rotacao_2d(rng.uniform(-MAX_ANG, MAX_ANG))
            X_a[i] = X_a[i] @ R.T
            shift = rng.integers(-MAX_SHIFT, MAX_SHIFT + 1)
            if shift != 0:
                X_a[i] = np.roll(X_a[i], shift, axis=0)
        X_a += rng.normal(0, 0.08, X_a.shape).astype(np.float32)
        aug_X.append(X_a.astype(np.float32))
        aug_y.append(y)
    return np.concatenate(aug_X), np.concatenate(aug_y)


def criar_conv1d():
    return keras.Sequential([
        layers.Input(shape=(JANELA, EIXOS)),
        layers.Conv1D(32, 5, activation='relu'),
        layers.MaxPooling1D(2),
        layers.Conv1D(64, 3, activation='relu'),
        layers.GlobalAveragePooling1D(),
        layers.Dropout(0.4),
        layers.Dense(32, activation='relu'),
        layers.Dense(len(CLASSES), activation='softmax')
    ])


def treinar_modelo(nome, criar_fn, X_train, y_train, X_val, y_val):
    print(f'\n{"=" * 50}')
    print(f'Treinando: {nome}')
    print('=' * 50)

    X_train_aug, y_train_aug = augmentar(X_train, y_train, fator=3)
    print(f'Apos augmentation: {len(X_train_aug)} amostras de treino')

    X_train_aug = deltas(X_train_aug)

    y_idx = np.argmax(y_train, axis=1)
    contagem = np.bincount(y_idx, minlength=len(CLASSES))
    pesos = {i: len(y_idx) / (len(CLASSES) * c) for i, c in enumerate(contagem)}
    print(f'Class weights: {pesos}')

    modelo = criar_fn()
    modelo.compile(
        optimizer=keras.optimizers.Adam(0.001),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    cb = [
        callbacks.EarlyStopping(monitor='val_accuracy', patience=25, restore_best_weights=True, verbose=1),
        callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=10, min_lr=0.00001, verbose=1)
    ]

    hist = modelo.fit(
        X_train_aug, y_train_aug,
        validation_data=(X_val, y_val),
        epochs=200,
        batch_size=32,
        class_weight=pesos,
        callbacks=cb,
        verbose=1
    )

    val_acc = max(hist.history['val_accuracy'])
    print(f'\n{nome} -> Melhor val_accuracy: {val_acc * 100:.1f}%')
    return modelo, val_acc


def avaliar(modelo, X_val, y_val):
    loss, acc = modelo.evaluate(X_val, y_val, verbose=0)
    print(f'Avaliacao final: acc={acc * 100:.1f}% loss={loss:.4f}')

    y_pred = np.argmax(modelo.predict(X_val, verbose=0), axis=1)
    y_true = np.argmax(y_val, axis=1)

    print('\nMatriz de confusao:')
    print(f'{"":>12} {"Pred DIR":>10} {"Pred ESQ":>10} {"Pred REP":>10}')
    for i, c in enumerate(CLASSES):
        linha = [int(np.sum((y_true == i) & (y_pred == j))) for j in range(len(CLASSES))]
        print(f'{c:>12} {linha[0]:>10} {linha[1]:>10} {linha[2]:>10}')


def limpar_layer(layer):
    config = dict(layer['config'])
    keras3_fields = [
        'module', 'registered_name', 'optional', 'sparse', 'ragged',
        'build_config', 'compile_config', 'synchronized',
        'quantization_config', 'keepdims', 'autocast',
    ]
    for f in keras3_fields:
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
    print('GPU:', tf.config.list_physical_devices('GPU'))

    X_train, X_val, y_train, y_val = carregar_dados()
    print(f'\nTreino: {len(X_train)} | Validacao: {len(X_val)}')

    X_val = deltas(X_val)

    modelo, val_acc = treinar_modelo('Conv1D', criar_conv1d, X_train, y_train, X_val, y_val)

    print(f'\n{"=" * 50}')
    print(f'Conv1D treinado com {val_acc * 100:.1f}% val_accuracy')
    print('=' * 50)

    avaliar(modelo, X_val, y_val)

    modelo.save(KERAS_H5)
    print(f'\nModelo Keras salvo em {KERAS_H5}')

    exportar_tfjs(modelo, SAIDA)
    print(f'Modelo TF.js salvo em {SAIDA}/ (model.json + weights.bin)')

    print('\nDeploy no servidor:')
    print(f'  scp -i C:/Users/Thiago/Downloads/ssh-key-2026-03-20.key {SAIDA}/model.json ubuntu@152.67.46.103:/tmp/')
    print(f'  scp -i C:/Users/Thiago/Downloads/ssh-key-2026-03-20.key {SAIDA}/weights.bin ubuntu@152.67.46.103:/tmp/')
    print('  ssh ... "sudo mv /tmp/model.json /tmp/weights.bin /opt/kinetix-relay/public/modelo/"')


if __name__ == '__main__':
    main()
