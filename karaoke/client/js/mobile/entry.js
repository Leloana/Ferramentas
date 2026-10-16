// Entrada do celular (partials/entry.html): um campo só, e o modo diz para onde vai o nome.
//  - Jogador: o nome é o apelido; entra na sala aberta (uma só = direto; a última em
//    que entrou, se ainda aberta; senão a lista de salas pelo nome).
//  - Sala: o nome é o da sala; este celular vira a tela da música (?role=display).
// Modo e nomes ficam lembrados: ao abrir de novo, é só tocar em Entrar.
import { savedMicName, saveMicName, savedEntry, saveEntry } from '../core/config.js';

const ROOM_NAME_MAX = 24;  // server/rooms.py ROOM_NAME_MAX
const NICK_MAX = 15;       // server/ws/room.py MAX_NICKNAME_LEN

function byId(id) {
    return document.getElementById(id);
}

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

function cleanName(raw) {
    return (raw || '').split(/\s+/).filter(Boolean).join(' ');
}

function currentMode() {
    const on = document.querySelector('.entry-toggle__btn[aria-selected="true"]');
    return on ? on.dataset.entryMode : 'player';
}

function setError(text) {
    const err = byId('entry-error');
    if (err) err.textContent = text || '';
}

function setBusy(busy) {
    const btn = byId('btn-entry');
    if (btn) btn.disabled = busy;
}

function showRooms(rooms) {
    const box = byId('entry-rooms');
    const form = byId('entry-form');
    const list = byId('entry-rooms-list');
    if (!box || !list) return;
    list.replaceChildren();
    rooms.forEach((room) => {
        const btn = el('button', 'btn entry-room');
        btn.type = 'button';
        btn.append(el('span', 'entry-room__name', room.id));
        if (room.song) btn.append(el('span', 'entry-room__song', room.song));
        btn.addEventListener('click', () => goPlayer(room.id));
        list.append(btn);
    });
    if (form) form.hidden = rooms.length > 0;
    box.hidden = !rooms.length;
}

function hideRooms() {
    const box = byId('entry-rooms');
    const form = byId('entry-form');
    if (box) box.hidden = true;
    if (form) form.hidden = false;
}

function setMode(mode) {
    document.querySelectorAll('.entry-toggle__btn').forEach((btn) => {
        btn.setAttribute('aria-selected', String(btn.dataset.entryMode === mode));
    });
    const input = byId('entry-name');
    const saved = savedEntry();
    if (input) {
        const isRoom = mode === 'room';
        input.placeholder = isRoom ? 'Nome da sala' : 'Seu apelido';
        input.setAttribute('aria-label', input.placeholder);
        input.maxLength = isRoom ? ROOM_NAME_MAX : NICK_MAX;
        input.autocomplete = isRoom ? 'off' : 'nickname';
        input.value = isRoom ? (saved.room_name || '') : savedMicName();
    }
    hideRooms();
    setError('');
    saveEntry({ mode });
}

function goPlayer(roomId) {
    saveEntry({ last_room: roomId });
    window.location.href = `/?role=mic&room=${encodeURIComponent(roomId)}`;
}

function goRoom(name) {
    window.location.href = `/?role=display&room=${encodeURIComponent(name)}`;
}

async function openRooms() {
    const resp = await fetch('/api/rooms', { cache: 'no-store' });
    if (!resp.ok) throw new Error('rooms');
    const data = await resp.json();
    return data.rooms || [];
}

async function enterAsPlayer(name) {
    saveMicName(name);  // o microfone entra sozinho com ele (mic-messages.js)
    const rooms = await openRooms();
    if (!rooms.length) {
        setError('Nenhuma sala aberta');
        return;
    }
    const last = (savedEntry().last_room || '').toLowerCase();
    const again = rooms.find((r) => r.id.toLowerCase() === last);
    if (again) {
        goPlayer(again.id);
    } else if (rooms.length === 1) {
        goPlayer(rooms[0].id);
    } else {
        showRooms(rooms);
    }
}

async function enterAsRoom(name) {
    const mine = (savedEntry().room_name || '').toLowerCase() === name.toLowerCase();
    if (!mine) {
        // nome em uso pela tela de outro aparelho (o servidor também recusa)
        const rooms = await openRooms();
        if (rooms.some((r) => r.id.toLowerCase() === name.toLowerCase())) {
            setError('Nome de sala em uso');
            return;
        }
    }
    saveEntry({ room_name: name });
    goRoom(name);
}

async function submit(event) {
    if (event) event.preventDefault();
    const input = byId('entry-name');
    const name = cleanName(input && input.value);
    const mode = currentMode();
    if (!name) {
        setError(mode === 'room' ? 'Digite o nome da sala' : 'Digite seu apelido');
        return;
    }
    setError('');
    setBusy(true);
    try {
        if (mode === 'room') await enterAsRoom(name);
        else await enterAsPlayer(name);
    } catch (e) {
        console.error('Entrada:', e);
        setError('Sem conexão com o servidor');
    } finally {
        setBusy(false);
    }
}

export function initEntry() {
    document.querySelectorAll('.entry-toggle__btn').forEach((btn) => {
        btn.addEventListener('click', () => setMode(btn.dataset.entryMode));
    });
    const form = byId('entry-form');
    if (form) form.addEventListener('submit', submit);
    const back = byId('btn-entry-rooms-back');
    if (back) back.addEventListener('click', hideRooms);
    const saved = savedEntry();
    setMode(saved.mode === 'room' || saved.taken ? 'room' : 'player');
    if (saved.taken) {
        // voltou da sala porque o nome já era de outra tela (ws-display.js)
        const input = byId('entry-name');
        if (input) input.value = saved.taken;
        setError('Nome de sala em uso');
        saveEntry({ taken: '' });
    }
}
