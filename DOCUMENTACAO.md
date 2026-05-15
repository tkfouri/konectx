# Documentacao Tecnica — Konectx

## Visao geral da arquitetura

O sistema e composto por tres camadas independentes que se comunicam via WebSocket:

```
CAMADA 1: Dispositivo (watch/celular)
  - Roda no navegador, sem instalacao
  - Carrega modelo TF.js pre-treinado (~200KB)
  - Le acelerometro a 60Hz via DeviceMotion API
  - Classifica gestos localmente (inferencia edge)
  - Envia apenas o resultado ("direita" ou "esquerda") ao relay

CAMADA 2: Relay (servidor na nuvem)
  - Stateless, nao processa IA
  - Gerencia salas (pareamento por codigo de 6 caracteres)
  - Roteia eventos WebSocket entre dispositivo e desktop
  - HTTPS via DuckDNS + Let's Encrypt

CAMADA 3: Desktop (app Electron no PC do usuario)
  - Cria sala automaticamente ao abrir
  - Recebe eventos de gesto roteados pelo relay
  - Converte em keystrokes via PowerShell SendKeys
  - Nenhuma dependencia de IA
```

## Arquivos do relay (relay/)

### server.js

Servidor principal. Responsabilidades:

- HTTPS: tenta carregar certificados de `/etc/letsencrypt/live/{domain}/`.
  Se nao encontrar, roda em HTTP (modo dev). Redirect automatico HTTP->HTTPS.

- Arquivos estaticos: serve `/public/` (homepage, watch, calibrar, modelo).

- API REST:
  - `POST /api/sala` — cria sala com codigo aleatorio de 6 chars (crypto.randomBytes).
    Retorna `{ codigo: "A3F2B1" }`.
  - `GET /api/status/:codigo` — verifica se pc/watch estao conectados na sala.
  - `GET /s/:codigo` — serve watch.html (rota amigavel para entrar na sala).

- WebSocket (Socket.io):
  - `entrar-sala { codigo, tipo }` — registra o socket na sala. Tipo e "pc" ou "watch".
    Usa socket.join() do Socket.io para criar rooms isoladas.
  - `gesto classe` — repassado para o outro membro da sala (watch->pc).
  - `amostra dados` — repassado para coleta de dados (calibracao watch->pc).
  - `contagem c` — sincroniza contador de amostras (pc->watch).
  - `disconnect` — limpa a sala se ambos saírem. Notifica o parceiro.

- Garbage collector: setInterval a cada 10 minutos remove salas vazias com mais de 1 hora.

### public/index.html

Homepage da Konectx. Funcoes:

- Apresentacao institucional (missao, visao, valores, servicos).
- Campo de entrada de codigo de sala (6 caracteres alfanumericos).
- Valida formato e redireciona para `/s/{codigo}` ao clicar Conectar.
- Design responsivo: funciona tanto no celular/relogio quanto no desktop.

### public/watch.html

Pagina que roda no dispositivo (relogio/celular). Fluxo:

1. Extrai o codigo da sala da URL (`/s/ABC123` -> `ABC123`).
2. Carrega modelo TF.js de `/modelo/model.json` (~200KB, 3 camadas densas).
3. Conecta ao relay via Socket.io e entra na sala como tipo "watch".
4. Ao tocar "Iniciar":
   - Solicita permissao do acelerometro (DeviceMotionEvent.requestPermission no iOS).
   - Ativa Wake Lock para impedir suspensao da tela.
   - Registra listener de `devicemotion`.
5. A cada frame do acelerometro:
   - Adiciona [x,y,z] ao buffer circular (max 80 frames = sliding window).
   - Quando buffer atinge 80: achata para vetor de 240, cria tensor, roda predict().
   - Se probabilidade > 97% e nao e repouso: emite evento `gesto` no socket.
   - Ativa cooldown de 1.5s (zera buffer, ignora novos dados).
6. Feedback visual: anel colorido muda de cor conforme o gesto detectado.

### public/calibrar.html

Pagina de gravacao de amostras. Usa a sala fixa "CALIBRAR". Fluxo:

1. Conecta ao relay e entra na sala CALIBRAR como "watch".
2. Tres botoes: Direita, Esquerda, Repouso.
3. Ao tocar um botao:
   - Inicia gravacao (flag `gravando = true`).
   - Acumula frames do acelerometro ate completar 80 (= 1 amostra).
   - Barra de progresso mostra o preenchimento.
4. Ao completar 80 frames:
   - Emite `amostra { label, features }` via socket.
   - O coletor.js no PC recebe e salva no dataset.json.
5. Contador sincronizado: o PC envia `contagem` de volta, exibida no relogio.

### public/modelo/

Contem o modelo pre-treinado:
- `model.json` — topologia da rede (3 camadas densas: 240->64->32->3).
- `weights.bin` — pesos serializados (~35KB).

Gerado pelo script `exportar-modelo.js`. Carregado pelo watch via `tf.loadLayersModel()`.

## Arquivos do desktop (desktop/)

### main.js

Processo principal do Electron. Cria janela 400x480, sem menu, nao redimensionavel.
Carrega ui.html com `nodeIntegration: true` para acessar `require()` e `child_process`.

### ui.html

Interface do app desktop. Fluxo:

1. Ao abrir, faz `POST /api/sala` no relay para obter codigo de sala.
2. Exibe o codigo de 6 caracteres na tela (tipografia monospace grande).
3. Instrui o usuario a acessar `konectx.tkfouri.is-a.dev` e digitar o codigo.
4. Conecta ao relay via Socket.io como tipo "pc".
5. Ao receber evento `gesto`:
   - Executa PowerShell via `child_process.exec()` para simular tecla.
   - `{RIGHT}` para direita, `{LEFT}` para esquerda.
   - Feedback visual: barra de status muda de cor conforme o gesto.
6. Reconexao automatica com retry de 5s em caso de erro.

## Arquivos de desenvolvimento (raiz)

### coletor.js

Script Node.js que roda no PC durante a fase de calibracao. Fluxo:

1. Conecta ao relay e entra na sala CALIBRAR como "pc".
2. Escuta evento `amostra` (enviado pelo calibrar.html no relogio).
3. Cada amostra recebida e appendada ao array e salva em `dataset.json`.
4. Envia `contagem` de volta para sincronizar o display do relogio.
5. Log no terminal mostra cada amostra recebida com totais por classe.

### exportar-modelo.js

Script de treino da rede neural. Fluxo:

1. Le `dataset.json` e filtra amostras com exatamente 80 frames.
2. One-hot encoding: direita=[1,0,0], esquerda=[0,1,0], repouso=[0,0,1].
3. Arquitetura: Dense(64,relu) -> Dense(32,relu) -> Dense(3,softmax).
4. Treino: 60 epocas, batch 16, shuffle, 15% validacao, Adam lr=0.001.
5. Exporta como `model.json` + `weights.bin` em `relay/public/modelo/`.
6. Usa `tf.io.withSaveHandler` para compatibilidade com tfjs puro (sem tfjs-node).

### dataset.json

Array de objetos com formato:
```json
{
  "label": "direita",
  "features": [[x,y,z], [x,y,z], ...]   // 80 vetores de 3 eixos
}
```

## Modelo de IA

Rede Neural Densa (Feedforward) com 3 camadas:

```
Entrada: 240 valores (80 frames x 3 eixos, achatados)
  |
Dense(64, ReLU)     — captura padroes basicos de aceleracao
  |
Dense(32, ReLU)     — combina padroes em features de nivel superior
  |
Dense(3, Softmax)   — probabilidade de cada classe (soma = 1.0)
  |
Saida: [P(direita), P(esquerda), P(repouso)]
```

- Funcao de perda: categorical crossentropy (padrao para classificacao multiclasse).
- Otimizador: Adam com learning rate 0.001.
- Threshold de confianca: 97% (so dispara gesto se a probabilidade maxima > 0.97).
- Cooldown: 1.5 segundos apos cada gesto detectado.

## Fluxo de rede

```
Watch -> Relay: WebSocket (wss://konectx.tkfouri.is-a.dev)
  Eventos: entrar-sala, gesto, amostra

Relay -> Desktop: WebSocket (wss://konectx.tkfouri.is-a.dev)
  Eventos: entrar-sala, gesto, parceiro-conectou/desconectou

Desktop -> Relay: HTTPS POST /api/sala (uma vez ao abrir)
  Resposta: { codigo: "ABC123" }
```

Trafego por gesto: ~15 bytes (string "direita" ou "esquerda" via Socket.io).
Dados brutos do sensor nunca saem do dispositivo.

## Seguranca

- HTTPS obrigatorio (Let's Encrypt, renovacao automatica via certbot).
- Nenhum dado biometrico ou sensorial e transmitido pela rede.
- Salas sao efemeras (codigo aleatorio, sem persistencia).
- Sem autenticacao de usuario (o codigo de sala e o unico segredo compartilhado).
- Sem banco de dados (relay e 100% stateless em memoria).
