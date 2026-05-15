# Konectx

Sistema de controle por gestos com smartwatch ou celular. Voce faz um gesto com o braco e o slide avanca — sem controle remoto, sem cliques, sem interrupcao.

Desenvolvido pela Konectx — empresa de inteligencia artificial aplicada.

## Como usar

So precisa de tres coisas: o app no PC, um celular ou relogio com navegador, e um PowerPoint aberto.

**1. Abra o app no computador**

Clique em `Konectx.exe` (instalador em `desktop/dist/`). O app abre uma janela mostrando um codigo de 6 caracteres, tipo `A3F2B1`.

**2. Conecte o celular ou relogio**

No navegador do dispositivo, acesse:

```
konectx.tkfouri.is-a.dev
```

Digite o codigo que apareceu no PC, toque em Conectar e depois em Iniciar. Pronto — o status no PC muda para "Dispositivo conectado".

**3. Apresente**

Abra seu PowerPoint em modo apresentacao e use os gestos:

| Gesto | Acao |
|---|---|
| Braco para a direita | Avanca o slide |
| Braco para a esquerda | Volta o slide |

E so isso. Toda a inteligencia roda dentro do navegador do dispositivo — nenhum dado do sensor sai do seu celular.

## Como funciona

```
Smartwatch (navegador)          Relay (nuvem)              PC (desktop)
  Acelerometro X,Y,Z     -->    Sala WebSocket     -->    PowerShell SendKeys
  TF.js inferencia local        Roteia eventos            Simula teclado
  Classifica gesto              Custo: R$0/mes            App Electron
```

A inteligencia artificial roda inteiramente no navegador do relogio. O servidor na nuvem
apenas roteia strings ("direita" / "esquerda") entre o dispositivo e o computador.
Nenhum dado bruto do sensor sai do dispositivo.

## Estrutura

```
konectx/
  relay/                      # Servidor na nuvem (Oracle Cloud)
    server.js                 # Express + Socket.io + HTTPS
    package.json
    public/
      index.html              # Homepage + campo de sala
      watch.html              # Pagina do relogio (TF.js + sensores)
      calibrar.html           # Pagina de gravacao de amostras
      modelo/                 # model.json + weights.bin
  desktop/                    # App do cliente (.exe)
    main.js                   # Electron
    ui.html                   # Interface com codigo da sala
    package.json
  calibrar-pc.js              # Recebe stream raw do relogio durante calibracao
  treinar.py                  # Treina os 3 modelos, escolhe o melhor e exporta
  dataset.json                # Dados de treino
  modelo_keras.h5             # Saida intermediaria do treino (formato Keras)
  modelo_tfjs/                # Saida final (model.json + weights.bin)
  package.json                # Deps Node de desenvolvimento
```

## Desenvolvimento

### Instalar dependencias

Node (relay, coletor, app desktop):
```bash
npm install                   # raiz (socket.io-client)
cd desktop && npm install     # electron + socket.io-client
```

Python (treino — TensorFlow/Keras + sklearn):
```bash
pip install tensorflow scikit-learn numpy
```

### Coletar dados de treino

Terminal 1 (PC):
```bash
npm run calibrar
```

No relogio/celular, acesse `https://konectx.tkfouri.is-a.dev/calibrar.html` e toque
em "Iniciar sensores". O relogio so transmite os dados brutos do acelerometro.

No PC, voce controla a gravacao pelo teclado:
- `D` — comeca a gravar um gesto de **direita** (80 frames)
- `E` — comeca a gravar um gesto de **esquerda** (80 frames)
- `R` — grava uma amostra de **repouso**
- `Q` — sair

Grave pelo menos 50 amostras de cada gesto (direita, esquerda) e 80 de repouso.
As amostras sao salvas automaticamente no `dataset.json` do PC.

### Treinar e exportar o modelo

```bash
npm run treinar
```

Treina tres arquiteturas (Conv1D, LSTM, hibrido), escolhe a de maior val_accuracy
e exporta para `modelo_tfjs/` no formato que o `watch.html` carrega.

Envia o modelo para o servidor:
```bash
scp -i chave.key modelo_tfjs/model.json ubuntu@IP:/tmp/
scp -i chave.key modelo_tfjs/weights.bin ubuntu@IP:/tmp/
ssh ... "sudo mv /tmp/model.json /tmp/weights.bin /opt/kinetix-relay/public/modelo/"
```

### Rodar o app desktop

```bash
npm run desktop
```

### Gerar o instalador (.exe)

```bash
cd desktop
npm run build
```

O instalador fica em `desktop/dist/`.

## Deploy do relay (Oracle Cloud)

Requisitos: VM Always Free (E2.1.Micro ou Ampere A1), Ubuntu 24.04, dominio via [is-a.dev](https://www.is-a.dev) + Let's Encrypt.

O subdominio `konectx.tkfouri.is-a.dev` foi registrado pelo servico gratuito **is-a.dev**
(via pull request no repositorio do projeto), apontando para o IP da VM Oracle.

```bash
sudo su
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs certbot iptables-persistent

# Abrir portas 80 e 443
iptables -I INPUT -p tcp --dport 80 -j ACCEPT
iptables -I INPUT -p tcp --dport 443 -j ACCEPT
netfilter-persistent save

# Emitir certificado SSL (apos o dominio is-a.dev ja apontar para esta VM)
certbot certonly --standalone -d konectx.tkfouri.is-a.dev --email email@email.com --agree-tos --non-interactive

# Copiar app
mkdir -p /opt/kinetix-relay
cp -r relay/* /opt/kinetix-relay/
cd /opt/kinetix-relay && npm install --production

# Servico systemd
cat > /etc/systemd/system/kinetix-relay.service << EOF
[Unit]
Description=Konectx Relay
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=/opt/kinetix-relay
Environment=DOMAIN=konectx.tkfouri.is-a.dev
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload && systemctl enable kinetix-relay && systemctl start kinetix-relay
```

## Tecnologias

| Componente | Tecnologia | Licenca |
|---|---|---|
| IA (treino) | TensorFlow.js | Apache 2.0 |
| IA (inferencia) | TensorFlow.js browser | Apache 2.0 |
| Relay server | Node.js + Express + Socket.io | MIT |
| Desktop app | Electron | MIT |
| Hospedagem | Oracle Cloud Always Free | Gratuito |
| Dominio | is-a.dev | Gratuito |
| SSL | Let's Encrypt | Gratuito |

Custo operacional: R$ 0,00/mes.

## Licenca

Codigo proprietario da Konectx. Todos os direitos reservados.
