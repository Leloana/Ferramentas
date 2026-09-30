// Lobby da partida: vagas de cantor com "+". Cada vaga = um cantor com o próprio
// microfone e um time (A–D).
//
// Não há "modo de jogo" para escolher: ele sai das vagas.
//   - cada um no seu time          → todos contra todos (solo, 1v1, 1v1v1...);
//   - duas vagas no mesmo time     → dupla (três, trio): barra do time em destaque
//                                    e uma barra discreta de cada membro.
// O servidor pontua por microfone (`active_players`); a soma por time é feita
// aqui no front (score-bars.js, pódio em game-view.js).

import { state } from './state.js';
import { openModal, closeModal } from './modal.js';
import { showToast } from './toast.js';
import { renderIcons, iconSvg } from './icons.js';

export const PC_MIC = 'PC_Local';
const MAX_SEATS = 6;
const MAX_TEAMS = 4; // uma barra por borda da TV
const TEAMS = ['A', 'B', 'C', 'D'];
const MODES = ['solo', '1v1', '1v1v1', '1v1v1v1'];
const GROUP_NAMES = { 2: 'Dupla', 3: 'Trio', 4: 'Quarteto' };

export function micLabel(mic) {
    return mic === PC_MIC ? 'Mic do dispositivo' : mic;
}

export function groupName(size) {
    return GROUP_NAMES[size] || `${size} vozes`;
}

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

function micWithIcon(cls, mic) {
    const span = el('span', cls);
    span.innerHTML = iconSvg('mic');
    span.append(document.createTextNode(' ' + micLabel(mic)));
    return span;
}

function availableMics() {
    return [PC_MIC].concat(state.lobbyMics || []);
}

function usedTeams(seats) {
    return TEAMS.filter((t) => seats.some((s) => s.team === t));
}

function teamSize(seats, team) {
    return seats.filter((s) => s.team === team).length;
}

// Times na ordem de A a D, cada um com seus microfones.
function groupsOf(seats) {
    return usedTeams(seats).map((team) => ({
        team,
        mics: seats.filter((s) => s.team === team).map((s) => s.mic),
    }));
}

// Nome do time para placar/pódio: "Marcelo" ou "Dupla A · Marcelo + Ana".
export function groupLabel(group) {
    const names = group.mics.map(micLabel).join(' + ');
    return group.mics.length > 1 ? `${groupName(group.mics.length)} ${group.team} · ${names}` : names;
}

// Escalação para iniciar a partida.
export function lobbyLineup() {
    const groups = groupsOf(state.lobbySeats);
    const mics = [];
    groups.forEach((g) => g.mics.forEach((m) => mics.push(m)));
    const hasTeams = groups.some((g) => g.mics.length > 1);
    const mode = hasTeams ? 'teams' : (MODES[Math.max(0, groups.length - 1)] || 'solo');
    // revezar versos: cada verso é de um time, em rodízio (duelo)
    const turns = !!state.lobbyTurns && groups.length > 1;
    return { mics, groups, mode, turns };
}

// Chamado a cada players_update: tira das vagas os celulares que saíram.
export function setAvailableMics(players) {
    state.lobbyMics = players.slice();
    const valid = availableMics();
    state.lobbySeats = state.lobbySeats.filter((s) => valid.indexOf(s.mic) !== -1);
    renderLobby();
}

function nextFreeTeam(seats) {
    const used = usedTeams(seats);
    const free = TEAMS.filter((t) => used.indexOf(t) === -1);
    return free.length && used.length < MAX_TEAMS ? free[0] : TEAMS[0];
}

// Ao abrir uma música: se ninguém está escalado, põe o 1º celular (ou o mic do PC).
export function ensureDefaultSeat() {
    if (!state.lobbySeats.length) {
        const mic = (state.lobbyMics && state.lobbyMics[0]) || PC_MIC;
        state.lobbySeats = [{ mic, team: 'A' }];
    }
    renderLobby();
}

// Botão "Time": passa para o próximo time (existente ou um novo, até D).
function cycleTeam(idx) {
    const seats = state.lobbySeats;
    const others = seats.filter((_, i) => i !== idx);
    const options = usedTeams(others);
    if (options.length < MAX_TEAMS) {
        const fresh = TEAMS.filter((t) => options.indexOf(t) === -1)[0];
        options.push(fresh);
    }
    options.sort();
    const cur = options.indexOf(seats[idx].team);
    seats[idx].team = options[(cur + 1) % options.length];
    renderLobby();
}

function summaryText(groups) {
    if (!groups.length) return 'Adicione pelo menos um cantor para começar.';
    if (groups.length === 1) {
        const g = groups[0];
        return g.mics.length > 1 ? `${groupName(g.mics.length)} cantando junto · ${groupLabel(g)}` : `Solo · ${groupLabel(g)}`;
    }
    const kind = (state.lobbyTurns ? 'Revezando versos' : (groups.some((g) => g.mics.length > 1) ? 'Times' : 'Disputa'));
    return `${kind} · ${groups.map((g) => (g.mics.length > 1 ? `${g.team} (${g.mics.map(micLabel).join(' + ')})` : micLabel(g.mics[0]))).join(' × ')}`;
}

export function renderLobby() {
    const wrap = document.getElementById('lobby-seats');
    if (!wrap) return;
    const seats = state.lobbySeats;
    const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.seatKey : undefined;

    wrap.replaceChildren();
    seats.forEach((seat, idx) => {
        const size = teamSize(seats, seat.team);
        const card = el('div', 'seat');
        card.dataset.team = String(TEAMS.indexOf(seat.team) + 1);

        const main = el('button', 'seat__main');
        main.type = 'button';
        main.dataset.seatKey = `mic-${idx}`;
        main.title = 'Trocar o microfone deste cantor';
        main.append(el('span', 'seat__num', `Cantor ${idx + 1}`), micWithIcon('seat__mic', seat.mic));
        main.addEventListener('click', () => openPicker(idx));

        const team = el('button', 'seat__team');
        team.type = 'button';
        team.dataset.seatKey = `team-${idx}`;
        team.title = 'Trocar de time (mesmo time = dupla/trio)';
        team.innerHTML = iconSvg('users');
        team.append(document.createTextNode(size > 1 ? ` ${groupName(size)} ${seat.team}` : ` Time ${seat.team}`));
        team.addEventListener('click', () => cycleTeam(idx));

        const remove = el('button', 'seat__remove');
        remove.type = 'button';
        remove.dataset.seatKey = `rm-${idx}`;
        remove.innerHTML = iconSvg('close');
        remove.setAttribute('aria-label', `Tirar o cantor ${idx + 1}`);
        remove.addEventListener('click', () => {
            state.lobbySeats.splice(idx, 1);
            renderLobby();
        });

        // Com um cantor só, "time" não faz sentido: o botão aparece a partir do 2º
        if (seats.length > 1) card.append(main, team, remove);
        else card.append(main, remove);
        wrap.append(card);
    });

    const freeMics = availableMics().filter((m) => !seats.some((s) => s.mic === m));
    if (seats.length < MAX_SEATS) {
        const add = el('button', 'seat seat--add');
        add.type = 'button';
        add.dataset.seatKey = 'add';
        const plus = el('span', 'seat--add__plus');
        plus.innerHTML = iconSvg('add');
        add.append(plus, el('span', 'seat--add__label', freeMics.length ? 'Adicionar cantor' : 'Conectar celular'));
        add.addEventListener('click', () => (freeMics.length ? openPicker(null) : openPairing()));
        wrap.append(add);
    }

    const summary = document.getElementById('lobby-summary');
    if (summary) summary.textContent = summaryText(groupsOf(seats));

    // Festa: sortear quem canta / a ordem, e revezar versos com 2+ times
    const shuffle = document.getElementById('btn-lobby-shuffle');
    if (shuffle) shuffle.hidden = availableMics().length < 2;
    const turns = document.getElementById('btn-lobby-turns');
    if (turns) {
        turns.hidden = groupsOf(seats).length < 2;
        turns.setAttribute('aria-pressed', String(!!state.lobbyTurns));
    }

    // mantém o foco do controle remoto no mesmo botão após re-renderizar
    if (focused !== undefined) {
        const again = wrap.querySelector(`[data-seat-key="${focused}"]`) || wrap.querySelector('[data-seat-key="add"]');
        if (again) again.focus();
    }
}

function openPairing() {
    const open = document.getElementById('btn-open-pairing');
    if (open) open.click();
}

// seatIdx null = nova vaga.
function openPicker(seatIdx) {
    const modal = document.getElementById('lobby-picker-modal');
    const list = document.getElementById('lobby-picker-list');
    const title = document.getElementById('lobby-picker-title');
    if (!modal || !list) return;

    title.textContent = seatIdx === null ? 'Novo cantor: qual microfone?' : `Cantor ${seatIdx + 1}: qual microfone?`;
    const current = seatIdx === null ? null : state.lobbySeats[seatIdx].mic;

    list.replaceChildren();
    availableMics().forEach((mic) => {
        const owner = state.lobbySeats.findIndex((s, i) => s.mic === mic && i !== seatIdx);
        const opt = el('button', 'mic-option');
        opt.type = 'button';
        opt.disabled = owner !== -1;
        if (mic === current) opt.setAttribute('aria-current', 'true');

        const hint = owner !== -1 ? `com o cantor ${owner + 1}` : 'livre';

        opt.append(micWithIcon('mic-option__name', mic), el('span', 'mic-option__hint', hint));
        opt.addEventListener('click', () => pick(seatIdx, mic));
        list.append(opt);
    });

    if (!(state.lobbyMics || []).length) {
        list.append(el('p', 'mic-options__empty', 'Nenhum celular conectado'));
    }

    openModal(modal);
}

function pick(seatIdx, mic) {
    if (seatIdx === null) state.lobbySeats.push({ mic, team: nextFreeTeam(state.lobbySeats) });
    else state.lobbySeats[seatIdx].mic = mic;
    closeModal('lobby-picker-modal');
    renderLobby();

    // Mic do dispositivo ainda sem permissão: pede agora (main.js cuida do getUserMedia).
    if (mic === PC_MIC && !state.localStreamForced) {
        const btn = document.getElementById('btn-force-pc-mic');
        if (btn) btn.click();
    }
}

// Sortear: com 1 cantor, escolhe um microfone ao acaso; com vários, embaralha
// quem fica em cada vaga (muda a ordem do revezamento).
function shuffleSeats() {
    const seats = state.lobbySeats;
    const pool = availableMics().slice();
    for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = pool[i]; pool[i] = pool[j]; pool[j] = tmp;
    }
    if (seats.length <= 1) {
        state.lobbySeats = [{ mic: pool[0], team: 'A' }];
    } else {
        seats.forEach((seat, i) => { seat.mic = pool[i % pool.length]; });
    }
    renderLobby();
    const first = state.lobbySeats[0];
    showToast(`Sorteado: ${micLabel(first.mic)}`, 'info');
}

export function initLobby() {
    const shuffle = document.getElementById('btn-lobby-shuffle');
    if (shuffle) shuffle.addEventListener('click', shuffleSeats);
    const turns = document.getElementById('btn-lobby-turns');
    if (turns) {
        turns.addEventListener('click', () => {
            state.lobbyTurns = !state.lobbyTurns;
            renderLobby();
        });
    }
    const pair = document.getElementById('btn-picker-pair');
    if (pair) {
        pair.addEventListener('click', () => {
            closeModal('lobby-picker-modal');
            openPairing();
        });
    }
    renderLobby();
    renderIcons();
}

// Antes de iniciar: pelo menos uma vaga.
export function validateLobby() {
    if (state.lobbySeats.length) return true;
    showToast('Adicione pelo menos um cantor no lobby.', 'error');
    return false;
}
