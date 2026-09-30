// Fila da noite: pedidos "quero cantar" (servidor: song_requests.py).
//
// TV: faixa "Próximas" na tela de músicas; tocar num pedido abre a música no
// lobby com quem pediu já escalado. No fim de jogo, contagem de 10 s abre a
// próxima sozinha (Cancelar segura).
// Celular: "Pedir música" (busca nas músicas prontas) e os próprios pedidos.
import { state } from './state.js';
import { iconSvg } from './icons.js';
import { showToast } from './toast.js';
import { micLabel, PC_MIC, renderLobby } from './lobby.js';
import { myRole } from './config.js';

const AUTO_NEXT_SEC = 10;

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

function send(msg) {
    const ws = myRole === 'mic' ? state.mobileWs : state.ws;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
        return true;
    }
    showToast('Sem conexão com a sala.', 'error');
    return false;
}

export function requestSong(songId, singer) {
    return send({ type: 'request_song', song_id: songId, singer });
}

export function cancelRequest(id) {
    return send({ type: 'cancel_request', id });
}

// --- TV ---

// Abre o pedido no lobby: música selecionada e quem pediu no 1º lugar.
export function startRequest(req) {
    const song = (state.allSongs || []).find((s) => s.id === req.song_id);
    if (!song || !state.selectSongFn) return;
    cancelRequest(req.id);
    state.selectSongFn(song);
    const mic = (state.lobbyMics || []).indexOf(req.singer) !== -1 ? req.singer : PC_MIC;
    state.lobbySeats = [{ mic, team: 'A' }];
    renderLobby();
}

function renderTvBar() {
    const bar = document.getElementById('requests-bar');
    const list = document.getElementById('requests-bar-list');
    if (!bar || !list) return;
    const reqs = state.songRequests || [];
    bar.hidden = !reqs.length;
    list.replaceChildren();
    reqs.forEach((req, idx) => {
        const item = el('li', 'request-chip');
        const open = el('button', 'request-chip__open');
        open.type = 'button';
        open.append(el('span', 'request-chip__place', `${idx + 1}º`), el('span', 'request-chip__who', micLabel(req.singer)),
            el('span', 'request-chip__song', req.title));
        open.addEventListener('click', () => startRequest(req));
        const rm = el('button', 'request-chip__remove');
        rm.type = 'button';
        rm.innerHTML = iconSvg('close');
        rm.setAttribute('aria-label', `Tirar o pedido de ${micLabel(req.singer)}`);
        rm.addEventListener('click', () => cancelRequest(req.id));
        item.append(open, rm);
        list.append(item);
    });
}

// Fim de jogo: "Próxima: Ana · Geni" com contagem; ao zerar abre no lobby.
export function showNextUp() {
    const box = document.getElementById('game-over-next');
    stopAutoNext();
    const next = (state.songRequests || [])[0];
    if (!box) return;
    if (!next) {
        box.hidden = true;
        return;
    }
    box.hidden = false;
    document.getElementById('next-up-text').textContent = `${micLabel(next.singer)} · ${next.title}`;
    const fill = document.getElementById('next-up-fill');
    let left = AUTO_NEXT_SEC;
    const tick = () => {
        if (fill) fill.style.width = `${(left / AUTO_NEXT_SEC) * 100}%`;
        const secs = document.getElementById('next-up-secs');
        if (secs) secs.textContent = `${left}s`;
        if (left <= 0) {
            goNext();
            return;
        }
        left -= 1;
    };
    tick();
    state.autoNextTimer = setInterval(tick, 1000);
}

export function stopAutoNext() {
    if (state.autoNextTimer) clearInterval(state.autoNextTimer);
    state.autoNextTimer = null;
}

async function goNext() {
    stopAutoNext();
    const next = (state.songRequests || [])[0];
    if (!next || !state.resetGameFn) return;
    await state.resetGameFn();
    startRequest(next);
}

export function initNextUpButtons() {
    const now = document.getElementById('btn-next-now');
    const cancel = document.getElementById('btn-next-cancel');
    if (now) now.addEventListener('click', goNext);
    if (cancel) {
        cancel.addEventListener('click', () => {
            stopAutoNext();
            const box = document.getElementById('game-over-next');
            if (box) box.hidden = true;
        });
    }
}

// --- Celular ---

function renderMicPanel() {
    const mine = document.getElementById('mic-requests');
    if (!mine) return;
    mine.replaceChildren();
    const reqs = state.songRequests || [];
    if (!reqs.length) {
        mine.append(el('p', 'profile-empty', 'Fila vazia'));
        return;
    }
    reqs.forEach((req, idx) => {
        const li = el('li', 'request-row');
        li.append(el('span', 'request-chip__place', `${idx + 1}º`), el('span', 'request-row__who', micLabel(req.singer)),
            el('span', 'request-row__song', req.title));
        if (req.singer === state.mobileNickname) {
            const rm = el('button', 'request-chip__remove');
            rm.type = 'button';
            rm.innerHTML = iconSvg('close');
            rm.setAttribute('aria-label', 'Cancelar pedido');
            rm.addEventListener('click', () => cancelRequest(req.id));
            li.append(rm);
        }
        mine.append(li);
    });
}

async function loadMicSongs() {
    if (state.micSongs) return state.micSongs;
    try {
        const resp = await fetch('/api/songs');
        const songs = await resp.json();
        state.micSongs = songs.filter((s) => s.is_ready);
    } catch (e) {
        state.micSongs = [];
    }
    return state.micSongs;
}

function renderMicSongs(query) {
    const list = document.getElementById('mic-request-songs');
    if (!list) return;
    const q = (query || '').trim().toLowerCase();
    const songs = (state.micSongs || []).filter((s) => !q || `${s.title} ${s.artist}`.toLowerCase().indexOf(q) !== -1);
    list.replaceChildren();
    songs.slice(0, 40).forEach((song) => {
        const btn = el('button', 'request-song');
        btn.type = 'button';
        btn.insertAdjacentHTML('beforeend', iconSvg('note', 'request-song__icon'));
        btn.append(el('span', 'request-song__title', song.title), el('span', 'request-song__artist', song.artist));
        btn.insertAdjacentHTML('beforeend', iconSvg('add', 'request-song__add'));
        btn.addEventListener('click', () => {
            if (!state.mobileNickname) {
                showToast('Entre com um apelido primeiro.', 'error');
                return;
            }
            requestSong(song.id);
        });
        list.append(btn);
    });
    if (!songs.length) list.append(el('p', 'profile-empty', 'Nada encontrado'));
}

export async function initMicRequests() {
    const search = document.getElementById('mic-request-search');
    if (!search) return;
    await loadMicSongs();
    renderMicSongs('');
    search.addEventListener('input', () => renderMicSongs(search.value));
    renderMicPanel();
}

// --- mensagens do servidor (TV e celular) ---

export function onRequestsUpdate(requests) {
    state.songRequests = requests || [];
    if (myRole === 'mic') renderMicPanel();
    else renderTvBar();
}
