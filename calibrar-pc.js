const { io } = require('socket.io-client');
const fs = require('fs');
const readline = require('readline');

const RELAY = 'https://konectx.tkfouri.is-a.dev';
const ARQUIVO = 'dataset.json';
const JANELA = 80;

let dataset = [];
if (fs.existsSync(ARQUIVO)) dataset = JSON.parse(fs.readFileSync(ARQUIVO));

let buffer = [];
let gravando = false;
let label = '';

const socket = io(RELAY);

socket.on('connect', () => {
    socket.emit('entrar-sala', { codigo: 'CALIBRAR', tipo: 'pc' });
    console.log('\n=== CALIBRACAO KONECTX ===');
    contagem();
    console.log('\nAguardando watch conectar...');
    console.log('Teclas: D = direita | E = esquerda | R = repouso | Q = sair\n');
});

socket.on('parceiro-conectou', () => {
    console.log('>>> Watch conectado! Pode gravar.\n');
});

socket.on('parceiro-desconectou', () => {
    console.log('>>> Watch desconectou.\n');
});

socket.on('raw', (dados) => {
    if (!gravando) return;
    buffer.push([parseFloat(dados.x), parseFloat(dados.y), parseFloat(dados.z)]);
    process.stdout.write('\r  Gravando: ' + buffer.length + '/' + JANELA + ' frames');

    if (buffer.length >= JANELA) {
        dataset.push({ label: label, features: buffer.slice(0, JANELA) });
        fs.writeFileSync(ARQUIVO, JSON.stringify(dataset, null, 2));
        gravando = false;
        buffer = [];
        console.log('  -> SALVO!');
        contagem();
        console.log('');
    }
});

socket.on('disconnect', () => console.log('Desconectado do relay'));

function contagem() {
    const d = dataset.filter(x => x.label === 'direita').length;
    const e = dataset.filter(x => x.label === 'esquerda').length;
    const r = dataset.filter(x => x.label === 'repouso').length;
    console.log('  D:' + d + ' | E:' + e + ' | R:' + r + ' | Total:' + dataset.length);
}

readline.emitKeypressEvents(process.stdin);
if (process.stdin.isTTY) process.stdin.setRawMode(true);

process.stdin.on('keypress', (ch, key) => {
    if (key && key.name === 'q') { console.log('\nSaindo...'); process.exit(0); }
    if (gravando) return;

    if (ch === 'd' || ch === 'D') { label = 'direita'; gravando = true; buffer = []; console.log('\n>> GRAVANDO DIREITA - faca o gesto!'); }
    if (ch === 'e' || ch === 'E') { label = 'esquerda'; gravando = true; buffer = []; console.log('\n>> GRAVANDO ESQUERDA - faca o gesto!'); }
    if (ch === 'r' || ch === 'R') { label = 'repouso'; gravando = true; buffer = []; console.log('\n>> GRAVANDO REPOUSO - fique parado!'); }
});