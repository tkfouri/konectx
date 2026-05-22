# Konectx

Sistema de controle por gestos com smartwatch ou celular. Você faz um gesto com o braço e o slide avança — sem controle remoto, sem cliques, sem interrupção.

Desenvolvido pela Konectx — empresa de inteligência artificial aplicada.

## Download

Instalador Windows mais recente: [github.com/tkfouri/konectx/releases/latest](https://github.com/tkfouri/konectx/releases/latest)

Baixe o `Konectx Setup x.y.z.exe` e execute. Após instalar, siga os passos abaixo.

## Como usar

Só precisa de três coisas: o app no PC, um celular ou relógio com navegador, e um PowerPoint aberto.

**1. Abra o app no computador**

Clique em `Konectx.exe` (instalador em `desktop/dist/`). O app abre uma janela mostrando um código de 6 caracteres, tipo `A3F2B1`.

**2. Conecte o celular ou relógio**

No navegador do dispositivo, acesse:

```
konectx.tkfouri.is-a.dev
```

Digite o código que apareceu no PC, toque em Conectar e depois em Iniciar. Pronto — o status no PC muda para "Dispositivo conectado".

**3. Apresente**

Abra seu PowerPoint em modo apresentação e use os gestos:

| Gesto | Ação |
|---|---|
| Braço para a direita | Avança o slide |
| Braço para a esquerda | Volta o slide |

É só isso. Toda a inteligência roda dentro do navegador do dispositivo — nenhum dado do sensor sai do seu celular.

## Como funciona

```
Smartwatch (navegador)          Relay (nuvem)              PC (desktop)
  Acelerômetro X,Y,Z     -->    Sala WebSocket     -->    PowerShell SendKeys
  TF.js inferência local        Roteia eventos            Simula teclado
  Classifica gesto              Custo: R$0/mês            App Electron
```

A inteligência artificial roda inteiramente no navegador do relógio. O servidor na nuvem
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
      watch.html              # Página do relógio (TF.js + sensores)
      calibrar.html           # Página de gravação de amostras
      modelo/                 # model.json + weights.bin
  desktop/                    # App do cliente (.exe)
    main.js                   # Electron
    ui.html                   # Interface com código da sala
    package.json
  calibrar-pc.js              # Recebe stream raw do relógio durante calibração
  treinar.py                  # Treina o modelo e exporta
  dataset.json                # Dados de treino
  modelo_keras.h5             # Saída intermediária do treino (formato Keras)
  modelo_tfjs/                # Saída final (model.json + weights.bin)
  package.json                # Deps Node de desenvolvimento
```

## Desenvolvimento

### Instalar dependências

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

No relógio/celular, acesse `https://konectx.tkfouri.is-a.dev/calibrar.html` e toque
em "Iniciar sensores". O relógio só transmite os dados brutos do acelerômetro.

No PC, você controla a gravação pelo teclado:
- `D` — começa a gravar um gesto de **direita** (80 frames)
- `E` — começa a gravar um gesto de **esquerda** (80 frames)
- `R` — grava uma amostra de **repouso**
- `Q` — sair

Grave pelo menos 50 amostras de cada gesto (direita, esquerda) e 80 de repouso.
As amostras são salvas automaticamente no `dataset.json` do PC.

### Treinar e exportar o modelo

```bash
npm run treinar
```

Treina uma rede Conv1D com normalização por janela (invariância à orientação)
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

Requisitos: VM Always Free (E2.1.Micro ou Ampere A1), Ubuntu 24.04, domínio via [is-a.dev](https://www.is-a.dev) + Let's Encrypt.

O subdomínio `konectx.tkfouri.is-a.dev` foi registrado pelo serviço gratuito **is-a.dev**
(via pull request no repositório do projeto), apontando para o IP da VM Oracle.

```bash
sudo su
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs certbot iptables-persistent

# Abrir portas 80 e 443
iptables -I INPUT -p tcp --dport 80 -j ACCEPT
iptables -I INPUT -p tcp --dport 443 -j ACCEPT
netfilter-persistent save

# Emitir certificado SSL (após o domínio is-a.dev já apontar para esta VM)
certbot certonly --standalone -d konectx.tkfouri.is-a.dev --email email@email.com --agree-tos --non-interactive

# Copiar app
mkdir -p /opt/kinetix-relay
cp -r relay/* /opt/kinetix-relay/
cd /opt/kinetix-relay && npm install --production

# Serviço systemd
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

| Componente | Tecnologia | Licença |
|---|---|---|
| IA (treino) | TensorFlow.js | Apache 2.0 |
| IA (inferência) | TensorFlow.js browser | Apache 2.0 |
| Relay server | Node.js + Express + Socket.io | MIT |
| Desktop app | Electron | MIT |
| Hospedagem | Oracle Cloud Always Free | Gratuito |
| Domínio | is-a.dev | Gratuito |
| SSL | Let's Encrypt | Gratuito |

Custo operacional: R$ 0,00/mês.

## Licença

Código proprietário da Konectx. Todos os direitos reservados.
