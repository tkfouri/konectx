const express = require('express');
const https = require('https');
const http = require('http');
const { Server } = require('socket.io');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');

const app = express();
const domain = process.env.DOMAIN || 'konectx.tkfouri.is-a.dev';

let server;
try {
    const certDir = '/etc/letsencrypt/live/' + domain;
    server = https.createServer({
        key: fs.readFileSync(path.join(certDir, 'privkey.pem')),
        cert: fs.readFileSync(path.join(certDir, 'fullchain.pem'))
    }, app);
    const redir = express();
    redir.use((req, res) => res.redirect('https://' + req.headers.host + req.url));
    http.createServer(redir).listen(80, () => console.log('HTTP redirect ativo'));
} catch (e) {
    console.log('Sem SSL:', e.message);
    server = http.createServer(app);
}

const io = new Server(server, { cors: { origin: '*' } });

app.use(express.static(path.join(__dirname, 'public')));
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST');
    next();
});

const salas = new Map();

function gerarCodigo() {
    return crypto.randomBytes(3).toString('hex').toUpperCase().slice(0, 6);
}

app.post('/api/sala', (req, res) => {
    const codigo = gerarCodigo();
    salas.set(codigo, { pc: null, watch: null, criado: Date.now() });
    res.json({ codigo });
});

app.get('/api/status/:codigo', (req, res) => {
    const sala = salas.get(req.params.codigo);
    if (sala === undefined) return res.status(404).json({ erro: 'Sala nao encontrada' });
    res.json({ pc: sala.pc !== null, watch: sala.watch !== null });
});

app.get('/s/:codigo', (req, res) => {
    const sala = salas.get(req.params.codigo);
    if (sala === undefined) return res.sendFile(path.join(__dirname, 'public', 'erro-sala.html'));
    if (sala.watch) return res.sendFile(path.join(__dirname, 'public', 'erro-ocupada.html'));
    res.sendFile(path.join(__dirname, 'public', 'watch.html'));
});

io.on('connection', (socket) => {

    socket.on('entrar-sala', ({ codigo, tipo }) => {
        if (codigo === 'CALIBRAR') {
            if (salas.get('CALIBRAR') === undefined) {
                salas.set('CALIBRAR', { pc: null, watch: null, criado: Date.now() });
            }
        } else if (salas.get(codigo) === undefined) {
            socket.emit('erro-sala', 'Sala nao existe');
            return;
        }

        const sala = salas.get(codigo);

        if (tipo === 'watch' && sala.watch && codigo !== 'CALIBRAR') {
            socket.emit('erro-sala', 'Sala ja tem um dispositivo conectado');
            return;
        }

        sala[tipo] = socket.id;
        socket.join(codigo);
        socket.data.codigo = codigo;
        socket.data.tipo = tipo;
        socket.to(codigo).emit('parceiro-conectou', tipo);
        console.log(tipo + ' entrou na sala ' + codigo);
    });

    socket.on('gesto', (classe) => {
        const codigo = socket.data.codigo;
        if (codigo === undefined) return;
        socket.to(codigo).emit('gesto', classe);
    });

    socket.on('raw', (dados) => {
        const codigo = socket.data.codigo;
        if (codigo === undefined) return;
        socket.to(codigo).emit('raw', dados);
    });

    socket.on('amostra', (dados) => {
        const codigo = socket.data.codigo;
        if (codigo === undefined) return;
        socket.to(codigo).emit('amostra', dados);
    });

    socket.on('contagem', (c) => {
        const codigo = socket.data.codigo;
        if (codigo === undefined) return;
        socket.to(codigo).emit('contagem', c);
    });

    socket.on('disconnect', () => {
        const { codigo, tipo } = socket.data || {};
        if (codigo === undefined || salas.get(codigo) === undefined) return;
        const sala = salas.get(codigo);
        sala[tipo] = null;
        socket.to(codigo).emit('parceiro-desconectou', tipo);
        console.log(tipo + ' saiu da sala ' + codigo);
        if (sala.pc === null && sala.watch === null && codigo !== 'CALIBRAR') {
            salas.delete(codigo);
        }
    });
});

setInterval(() => {
    const agora = Date.now();
    for (const [codigo, sala] of salas) {
        if (sala.pc === null && sala.watch === null && agora - sala.criado > 3600000) {
            salas.delete(codigo);
        }
    }
}, 600000);

const porta = server instanceof https.Server ? 443 : 3000;
server.listen(porta, () => console.log('Relay rodando na porta ' + porta));
