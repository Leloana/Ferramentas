// Perfil dos cantores: ranking (lista de cantores) e perfil de um apelido.
// Usado no modal "Cantores" da TV e na aba "Perfil" do celular-microfone.
// Dados de /api/players (players.py no servidor).
import { iconSvg } from '../core/icons.js';
import { openAnnotationFor } from './annotate.js';
import { toggleReplay, stopReplay } from '../audio/replay.js';

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

function pct(v) {
    return typeof v === 'number' ? `${Math.round(v)}%` : '—';
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}

function stat(label, value, icon) {
    const box = el('div', 'profile-stat');
    if (icon) box.insertAdjacentHTML('beforeend', iconSvg(icon, 'profile-stat__icon'));
    box.append(el('span', 'profile-stat__value', value), el('span', 'profile-stat__label', label));
    return box;
}

export async function fetchPlayers() {
    const resp = await fetch('/api/players');
    if (!resp.ok) throw new Error('Falha ao carregar os cantores');
    return (await resp.json()).players || [];
}

export async function fetchProfile(name) {
    const resp = await fetch(`/api/players/${encodeURIComponent(name)}`);
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error('Falha ao carregar o perfil');
    return resp.json();
}

// Lista de cantores (ranking pela média); onPick(name) abre o perfil.
export function renderPlayersList(container, playersList, onPick) {
    stopReplay();  // saiu do perfil: a gravação que tocava para
    container.replaceChildren();
    if (!playersList.length) {
        container.append(el('p', 'profile-empty', 'Ninguém cantou ainda'));
        return;
    }
    const ranked = playersList.slice().sort((a, b) => b.avg - a.avg);
    const list = el('ol', 'players-list');
    ranked.forEach((p, idx) => {
        const item = el('li');
        const row = el('button', 'player-row');
        row.type = 'button';
        row.append(
            el('span', 'player-row__place', `${idx + 1}º`),
            el('span', 'player-row__name', p.name),
            el('span', 'player-row__meta', `${p.games} ${p.games === 1 ? 'música' : 'músicas'}`),
            el('span', 'player-row__score', pct(p.avg)),
        );
        row.addEventListener('click', () => onPick(p.name));
        item.append(row);
        list.append(item);
    });
    container.append(list);
}

// Perfil completo: resumo, recordes por música e últimas partidas.
export function renderProfile(container, detail) {
    stopReplay();
    container.replaceChildren();
    if (!detail) {
        container.append(el('p', 'profile-empty', 'Ainda sem partidas'));
        return;
    }
    const head = el('div', 'profile-head');
    head.insertAdjacentHTML('beforeend', iconSvg('user', 'profile-head__avatar'));
    head.append(el('h3', 'profile-head__name', detail.name));
    container.append(head);

    const stats = el('div', 'profile-stats');
    stats.append(
        stat('músicas', String(detail.games), 'note'),
        stat('média', pct(detail.avg), 'gauge'),
        stat('recorde', pct(detail.best), 'trophy'),
    );
    if (typeof detail.avg_pitch === 'number') stats.append(stat('tom', pct(detail.avg_pitch), 'pitch'));
    container.append(stats);

    if (detail.records && detail.records.length) {
        container.append(el('h4', 'profile-section', 'Recordes'));
        const list = el('ol', 'profile-records');
        detail.records.slice(0, 12).forEach((r) => {
            const li = el('li', 'profile-record');
            li.append(
                el('span', 'profile-record__name', r.name || r.song_id),
                el('span', 'profile-record__times', r.times > 1 ? `${r.times}×` : ''),
                el('span', 'profile-record__best', pct(r.best)),
            );
            list.append(li);
        });
        container.append(list);
    }

    // Partidas gravadas: tocar abre a análise verso a verso (a mesma do fim de jogo)
    const sessions = el('div', 'profile-sessions');
    container.append(sessions);
    renderSessions(sessions, detail.name);

    if (detail.recent && detail.recent.length) {
        container.append(el('h4', 'profile-section', 'Últimas'));
        const list = el('ol', 'profile-recent');
        detail.recent.forEach((r) => {
            const li = el('li', 'profile-record');
            li.append(
                el('span', 'profile-record__name', r.name),
                el('span', 'profile-record__times', formatDate(r.date)),
                el('span', 'profile-record__best', pct(r.score)),
            );
            list.append(li);
        });
        container.append(list);
    }
}

async function renderSessions(box, name) {
    let games;
    try {
        const resp = await fetch(`/api/players/${encodeURIComponent(name)}/recordings`);
        if (!resp.ok) return;
        games = (await resp.json()).recordings || [];
    } catch (e) {
        return;  // sem gravações: a seção simplesmente não aparece
    }
    if (!games.length) return;
    box.append(el('h4', 'profile-section', 'Partidas gravadas'));
    const list = el('ol', 'profile-recent');
    games.slice(0, 30).forEach((g) => {
        const li = el('li', 'profile-session-item');

        // play: a voz gravada por cima do instrumental (mesmo "ouvir" do fim de jogo)
        const play = el('button', 'btn btn--ghost btn-replay profile-session__play');
        play.type = 'button';
        play.title = 'Ouvir a apresentação';
        play.setAttribute('aria-label', `Ouvir ${g.song_title}`);
        play.innerHTML = iconSvg('play');
        play.addEventListener('click', () => {
            const starting = !play.classList.contains('is-playing');
            toggleReplay({
                recordingId: g.id,
                player: name,
                songId: g.song_id,
                button: play,
                onStop: () => { play.innerHTML = iconSvg('play'); },
            });
            if (starting) play.innerHTML = iconSvg('pause');
        });
        li.append(play);

        const row = el('button', 'profile-record profile-session');
        row.type = 'button';
        row.title = 'Ver os versos';
        row.append(
            el('span', 'profile-record__name', g.song_title),
            el('span', 'profile-record__times', formatDate(g.date)),
            el('span', 'profile-record__best', pct(g.score)),
        );
        row.insertAdjacentHTML('beforeend', iconSvg('next', 'profile-session__go'));
        row.addEventListener('click', () => openAnnotationFor(g.id, name));
        li.append(row);
        list.append(li);
    });
    box.append(list);
}
