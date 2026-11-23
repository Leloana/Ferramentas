// Aviso na tela da sala quando um celular muda algo pela aba Sala ("Lelo mudou o
// tom: +2"), também durante a música. Um aviso só, pequeno, no topo: o mesmo
// celular arrastando o mesmo controle atualiza o aviso em vez de empilhar.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';

const SHOW_MS = 3200;

const SCRIPT_NAMES = { original: 'original', romaji: 'romaji', both: 'original + romaji' };

function pct(v) {
    return `${Math.round((Number(v) || 0) * 100)}%`;
}

// Texto do que mudou (depois do nome de quem mudou); null = não avisa
export function describeRemote(cmd, extra) {
    const info = extra || {};
    switch (cmd.action) {
        case 'select_song': return info.title ? `escolheu ${info.title}` : 'trocou a música';
        case 'seats': return 'mudou os cantores';
        case 'turns': return cmd.value ? 'ligou o revezamento de versos' : 'desligou o revezamento de versos';
        case 'scoring_mode': return `mudou a pontuação: ${cmd.value === 'words' ? 'só palavras' : 'palavras + tempo'}`;
        case 'transpose': return `mudou o tom: ${cmd.value === 0 ? 'normal' : (cmd.value > 0 ? '+' : '') + cmd.value}`;
        case 'speed': return `mudou a velocidade: ${Number(cmd.value).toFixed(2)}x`;
        case 'volume': return `mudou o volume da música: ${pct(cmd.value)}`;
        case 'guide_volume': return `mudou a voz guia: ${pct(cmd.value)}`;
        case 'pause': return info.paused ? 'pausou a música' : 'retomou a música';
        case 'stop': return 'encerrou a música';
        case 'start': return 'deu o play';
        case 'lobby': return 'voltou ao lobby';
        case 'lyrics_script': return `mudou a letra: ${SCRIPT_NAMES[cmd.value] || cmd.value}`;
        case 'sync_mode': return `mudou a sincronia: ${cmd.value === 'verse' ? 'verso inteiro' : 'palavra por palavra'}`;
        default: return null;
    }
}

function noticeEl() {
    let el = document.getElementById('remote-notice');
    if (!el) {
        el = document.createElement('div');
        el.id = 'remote-notice';
        el.className = 'remote-notice';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        document.body.appendChild(el);
    }
    return el;
}

export function showRemoteNotice(cmd, extra) {
    const what = describeRemote(cmd, extra);
    if (!what || !cmd.from) return;
    const el = noticeEl();
    el.replaceChildren();
    el.insertAdjacentHTML('beforeend', iconSvg('mic', 'remote-notice__icon'));
    const who = document.createElement('strong');
    who.className = 'remote-notice__who';
    who.textContent = cmd.from;  // apelido vem do celular: só texto
    const text = document.createElement('span');
    text.textContent = ' ' + what;
    el.append(who, text);
    el.dataset.visible = 'true';
    clearTimeout(state.remoteNoticeTimer);
    state.remoteNoticeTimer = setTimeout(() => { el.dataset.visible = 'false'; }, SHOW_MS);
}
