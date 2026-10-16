// Aba "Sala" do celular: comandar a TV daqui (servidor: server/remote_control.py;
// TV: lobby/remote-control.js).
//
// 1) Música da vez: busca pelo nome; trava enquanto ela toca. Quando acaba, a
//    1ª da fila entra no lugar (a TV faz isso no fim de jogo) e basta dar play.
// 2) Configuração da sala: cantores (microfones conectados), times, revezar
//    versos, pontuação; tom, velocidade, volume da música e da voz guia,
//    pausar e encerrar valem tocando.
// 3) Iniciar: bloqueado com o motivo (TV fora, música tocando, GPU gerando letra,
//    sem música ou sem cantor). O servidor confere as mesmas travas.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { showToast } from '../core/toast.js';
import { openModal } from '../ui/modal.js';
import { songMatcher } from '../core/song-search.js';
import { micLabel } from '../lobby/lobby.js';
import { setLyricsScriptAvailable } from '../game/lyrics-script.js';
import { loadMicSongs } from '../lobby/requests.js';

const TEAMS = ['A', 'B', 'C', 'D'];
const MAX_SEATS = 6;
const MAX_RESULTS = 40;

const byId = (id) => document.getElementById(id);

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

function remote(action, extra) {
    const ws = state.mobileWs;
    if (!state.mobileNickname) {
        showToast('Entre com um apelido primeiro.', 'error');
        return false;
    }
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        showToast('Sem conexão com a sala.', 'error');
        return false;
    }
    const msg = { type: 'remote', action };
    Object.keys(extra || {}).forEach((k) => { msg[k] = extra[k]; });
    ws.send(JSON.stringify(msg));
    return true;
}

function rs() {
    return state.remoteState || {};
}

function playing() {
    return !!rs().in_game;
}

// Motivo para não iniciar agora (null = pode)
function startBlock() {
    const s = rs();
    if (!state.mobileNickname) return 'Entre com um apelido';
    if (!s.has_display) return 'TV desconectada';
    if (s.in_game) return null;  // botão vira "Tocando"
    const gpu = state.gpuBlock || s.gpu_busy;
    if (gpu) return `GPU ocupada · gerando a letra de ${gpu}`;
    if (!s.song) return 'Escolha a música da vez';
    if (!(s.seats || []).length) return 'Adicione um cantor na configuração da sala';
    return null;
}

function seatsSummary(seats) {
    if (!seats.length) return 'Ninguém cantando';
    const teams = TEAMS.filter((t) => seats.some((s) => s.team === t));
    const names = teams.map((t) => seats.filter((s) => s.team === t).map((s) => micLabel(s.mic)).join(' + '));
    let text = names.join(teams.length > 1 ? ' × ' : '');
    if (teams.length > 1 && rs().turns) text += ' · revezando';
    return text;
}

// --- 1) música da vez ---

function closePicker() {
    const drop = byId('room-song-drop');
    if (drop) drop.hidden = true;
    const btn = byId('room-song-current');
    if (btn) btn.setAttribute('aria-expanded', 'false');
}

async function openPicker() {
    if (playing()) {
        showToast('Espere a música acabar para trocar.', 'error');
        return;
    }
    const drop = byId('room-song-drop');
    if (!drop.hidden) {
        closePicker();
        return;
    }
    drop.hidden = false;
    byId('room-song-current').setAttribute('aria-expanded', 'true');
    const search = byId('room-song-search');
    search.value = '';
    search.focus();
    state.micSongs = null;  // pega as que ficaram prontas desde a última vez
    await loadMicSongs();
    renderResults(search.value);  // o que já foi digitado enquanto carregava
}

function renderResults(query) {
    const list = byId('room-song-results');
    if (!list) return;
    const current = rs().song && rs().song.id;
    const songs = (state.micSongs || []).filter(songMatcher(query));
    list.replaceChildren();
    songs.slice(0, MAX_RESULTS).forEach((song) => {
        const btn = el('button', 'request-song');
        btn.type = 'button';
        if (song.id === current) btn.setAttribute('aria-current', 'true');
        btn.insertAdjacentHTML('beforeend', iconSvg('note', 'request-song__icon'));
        const title = el('span', 'request-song__title', song.title);
        if (song.title_romaji) title.append(el('span', 'request-song__romaji', song.title_romaji));
        btn.append(title, el('span', 'request-song__artist', song.album ? `${song.artist} · ${song.album}` : song.artist));
        btn.insertAdjacentHTML('beforeend', iconSvg(song.id === current ? 'check' : 'play', 'request-song__add'));
        btn.addEventListener('click', () => {
            if (remote('select_song', { song_id: song.id })) closePicker();
        });
        list.append(btn);
    });
    if (!songs.length) list.append(el('p', 'profile-empty', 'Nada encontrado'));
}

// --- 2) configuração da sala ---

function sendSeats(seats) {
    remote('seats', { seats });
}

function cycleTeam(idx) {
    const seats = (rs().seats || []).map((s) => ({ mic: s.mic, team: s.team }));
    const others = seats.filter((_, i) => i !== idx);
    const options = TEAMS.filter((t) => others.some((s) => s.team === t));
    if (options.length < TEAMS.length) options.push(TEAMS.filter((t) => options.indexOf(t) === -1)[0]);
    options.sort();
    seats[idx].team = options[(options.indexOf(seats[idx].team) + 1) % options.length];
    sendSeats(seats);
}

function addSeat(mic) {
    const seats = (rs().seats || []).map((s) => ({ mic: s.mic, team: s.team }));
    const used = TEAMS.filter((t) => seats.some((s) => s.team === t));
    const free = TEAMS.filter((t) => used.indexOf(t) === -1);
    seats.push({ mic, team: free.length ? free[0] : 'A' });
    sendSeats(seats);
}

function removeSeat(idx) {
    const seats = (rs().seats || []).filter((_, i) => i !== idx).map((s) => ({ mic: s.mic, team: s.team }));
    sendSeats(seats);
}

function renderSettings() {
    const s = rs();
    const locked = playing();
    const seats = s.seats || [];
    const lock = byId('room-settings-lock');
    if (lock) lock.hidden = !locked;

    const list = byId('room-seats');
    if (list) {
        list.replaceChildren();
        seats.forEach((seat, idx) => {
            const size = seats.filter((x) => x.team === seat.team).length;
            const li = el('li', 'room-seat');
            li.dataset.team = String(TEAMS.indexOf(seat.team) + 1);
            const name = el('span', 'room-seat__name');
            name.innerHTML = iconSvg('mic');
            name.append(document.createTextNode(' ' + micLabel(seat.mic)));
            li.append(name);
            if (seats.length > 1) {
                const team = el('button', 'room-seat__team', size > 1 ? `Junto ${seat.team}` : `Time ${seat.team}`);
                team.type = 'button';
                team.disabled = locked;
                team.addEventListener('click', () => cycleTeam(idx));
                li.append(team);
            }
            const rm = el('button', 'room-seat__remove');
            rm.type = 'button';
            rm.innerHTML = iconSvg('close');
            rm.setAttribute('aria-label', `Tirar ${micLabel(seat.mic)}`);
            rm.disabled = locked;
            rm.addEventListener('click', () => removeSeat(idx));
            li.append(rm);
            list.append(li);
        });
        if (!seats.length) list.append(el('li', 'profile-empty', 'Ninguém cantando'));
    }

    const freeBox = byId('room-free-mics');
    if (freeBox) {
        freeBox.replaceChildren();
        const free = (s.mics || []).filter((m) => !seats.some((x) => x.mic === m));
        if (seats.length < MAX_SEATS) {
            free.forEach((mic) => {
                const btn = el('button', 'room-free-mic');
                btn.type = 'button';
                btn.disabled = locked;
                btn.innerHTML = iconSvg('add');
                btn.append(document.createTextNode(' ' + micLabel(mic)));
                btn.addEventListener('click', () => addSeat(mic));
                freeBox.append(btn);
            });
        }
        if (!free.length && !seats.length) freeBox.append(el('p', 'profile-empty', 'Nenhum celular conectado'));
    }

    const turns = byId('btn-room-turns');
    if (turns) {
        const teams = TEAMS.filter((t) => seats.some((x) => x.team === t)).length;
        turns.hidden = teams < 2;
        turns.disabled = locked;
        turns.setAttribute('aria-pressed', String(!!s.turns));
    }
    const scoring = byId('btn-room-scoring');
    if (scoring) {
        const words = s.scoring_mode === 'words';
        scoring.disabled = locked;
        scoring.setAttribute('aria-pressed', String(words));
        scoring.innerHTML = iconSvg(words ? 'score-words' : 'metronome');
        scoring.append(el('span', null, words ? 'Só palavras' : 'Palavras + tempo'));
    }
    // sliders: o que está sendo arrastado agora não é sobrescrito pelo eco da TV
    document.querySelectorAll('#room-settings-modal [data-sound]').forEach((slider) => {
        const key = slider.dataset.sound;
        const value = s[key];
        if (typeof value !== 'number' || slider === state.roomSliderDragging) return;
        slider.value = String(value);
        paintSoundValue(key, value);
    });
    const actions = byId('room-playing-actions');
    if (actions) actions.hidden = !locked;
    const pause = byId('room-pause-label');
    if (pause) pause.textContent = s.paused ? 'Retomar' : 'Pausar';
}

const SOUND_SEND_MS = 150;

function soundLabel(key, value) {
    if (key === 'transpose') return value === 0 ? 'Normal' : `${value > 0 ? '+' : ''}${value}`;
    if (key === 'speed') return `${value.toFixed(2)}x`;
    return `${Math.round(value * 100)}%`;
}

function paintSoundValue(key, value) {
    const label = document.querySelector(`#room-settings-modal [data-sound-value="${key}"]`);
    if (label) label.textContent = soundLabel(key, value);
}

// Arrastar: manda o valor no máximo a cada SOUND_SEND_MS enquanto arrasta e o final ao soltar
function initSoundSliders() {
    document.querySelectorAll('#room-settings-modal [data-sound]').forEach((slider) => {
        const key = slider.dataset.sound;
        const read = () => (key === 'transpose' ? parseInt(slider.value, 10) : parseFloat(slider.value));
        const send = () => {
            slider._lastSent = Date.now();
            remote(key, { value: read() });
        };
        slider.addEventListener('input', () => {
            state.roomSliderDragging = slider;
            paintSoundValue(key, read());
            clearTimeout(slider._sendTimer);
            const wait = SOUND_SEND_MS - (Date.now() - (slider._lastSent || 0));
            if (wait <= 0) send();
            else slider._sendTimer = setTimeout(send, wait);
        });
        slider.addEventListener('change', () => {
            clearTimeout(slider._sendTimer);
            send();
            state.roomSliderDragging = null;
        });
    });
}

// --- painel ---

function setStatus(text, tone) {
    const chip = byId('room-status');
    if (!chip) return;
    chip.hidden = !text;
    chip.textContent = text || '';
    if (tone) chip.dataset.tone = tone;
}

export function renderRoomPanel() {
    const s = rs();
    const song = s.song;
    const title = byId('room-song-title');
    if (!title) return;
    title.textContent = song ? song.title : 'Escolher música';
    byId('room-song-artist').textContent = song ? song.artist : '';
    const picker = byId('room-song-picker');
    picker.classList.toggle('song-picker--locked', playing());
    picker.classList.toggle('song-picker--empty', !song);
    if (playing()) closePicker();

    byId('room-settings-summary').textContent = seatsSummary(s.seats || []);
    setLyricsScriptAvailable(!!(song && song.japanese_script));

    const start = byId('btn-room-start');
    const label = byId('room-start-label');
    const note = byId('room-start-note');
    const block = startBlock();
    if (playing()) {
        start.disabled = true;
        label.textContent = s.paused ? 'Pausada' : 'Tocando';
        setStatus(s.paused ? 'Pausada' : 'Tocando', 'sage');
    } else {
        start.disabled = !!block;
        label.textContent = 'Iniciar';
        setStatus(s.has_display ? (state.gpuBlock || s.gpu_busy ? 'GPU ocupada' : '') : 'TV desconectada', 'rose');
    }
    note.hidden = !block;
    note.textContent = block || '';
    renderSettings();
}

export function onRemoteState(data) {
    state.remoteState = data;
    renderRoomPanel();
}

export function initRoomPanel() {
    const current = byId('room-song-current');
    if (!current) return;
    current.addEventListener('click', openPicker);
    const search = byId('room-song-search');
    search.addEventListener('input', () => renderResults(search.value));

    byId('btn-room-settings').addEventListener('click', () => {
        renderSettings();
        openModal(byId('room-settings-modal'));
    });
    byId('btn-room-start').addEventListener('click', () => {
        const block = startBlock();
        if (block) {
            showToast(block, 'error');
            return;
        }
        if (remote('start')) {
            byId('room-start-label').textContent = 'Iniciando...';
            byId('btn-room-start').disabled = true;
        }
    });

    byId('btn-room-turns').addEventListener('click', () => remote('turns', { value: !rs().turns }));
    byId('btn-room-scoring').addEventListener('click', () => remote('scoring_mode', { value: rs().scoring_mode === 'words' ? 'timing' : 'words' }));
    initSoundSliders();
    byId('btn-room-pause').addEventListener('click', () => remote('pause'));
    byId('btn-room-stop').addEventListener('click', () => {
        if (confirm('Encerrar a música agora? A nota desta partida não é salva.')) remote('stop');
    });

    const queueAdd = byId('btn-room-queue-add');
    queueAdd.addEventListener('click', async () => {
        const box = byId('room-queue-add');
        box.hidden = !box.hidden;
        queueAdd.setAttribute('aria-expanded', String(!box.hidden));
        if (!box.hidden) {
            state.micSongs = null;
            await loadMicSongs();
            const input = byId('mic-request-search');
            input.dispatchEvent(new Event('input'));
            input.focus();
        }
    });

    // GPU ocupada muda sem mensagem do servidor: vem do polling da fila (queue-view.js)
    state.onGpuBlockChange = renderRoomPanel;
    renderRoomPanel();
}
