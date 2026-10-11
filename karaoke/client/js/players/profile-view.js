// Perfil dos cantores: ranking (lista de cantores) e perfil de um apelido.
// Usado no modal "Cantores" da TV e na aba "Perfil" do celular-microfone.
// Dados de /api/players (players.py no servidor).
import { iconSvg } from '../core/icons.js';
import { openAnnotationFor } from './annotate.js';
import { toggleReplay, stopReplay } from '../audio/replay.js';
import { showToast } from '../core/toast.js';
import { avatarNode, fetchAvatarVersion, uploadAvatar, removeAvatar } from './avatar.js';

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
        const who = el('span', 'player-row__who');
        who.append(avatarNode(p.name, p.avatar, 'avatar--row'), el('span', 'player-row__name', p.name));
        row.append(
            el('span', 'player-row__place', `${idx + 1}º`),
            who,
            el('span', 'player-row__meta', `${p.games} ${p.games === 1 ? 'música' : 'músicas'}`),
            el('span', 'player-row__score', pct(p.avg)),
        );
        row.addEventListener('click', () => onPick(p.name));
        item.append(row);
        list.append(item);
    });
    container.append(list);
}

// Topo do perfil: foto grande no centro e o apelido embaixo. `editable` (o próprio
// cantor, no celular): botão de câmera sobre a foto troca; "Tirar foto" embaixo.
function renderHead(name, version, opts) {
    const head = el('div', 'profile-hero');
    const photo = el('div', 'profile-hero__photo');
    photo.append(avatarNode(name, version, 'profile-hero__avatar'));
    head.append(photo, el('h3', 'profile-hero__name', name));
    if (!opts.editable) return head;

    const input = el('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.hidden = true;
    const pick = el('button', 'profile-hero__camera');
    pick.type = 'button';
    pick.title = version ? 'Trocar foto' : 'Pôr foto';
    pick.setAttribute('aria-label', pick.title);
    pick.innerHTML = iconSvg('camera');
    pick.addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
        const file = input.files && input.files[0];
        if (!file) return;
        pick.disabled = true;
        try {
            await uploadAvatar(name, file);
            if (opts.onChanged) opts.onChanged();
        } catch (e) {
            showToast(e.message, 'error');
            pick.disabled = false;
        }
    });
    photo.append(pick, input);
    if (version) {
        const drop = el('button', 'profile-hero__drop', 'Tirar foto');
        drop.type = 'button';
        drop.addEventListener('click', async () => {
            await removeAvatar(name);
            if (opts.onChanged) opts.onChanged();
        });
        head.append(drop);
    }
    return head;
}

// Lista que abre e fecha (details/summary: o Enter do controle da TV também abre)
function collapsible(title, count, content, open) {
    const box = el('details', 'profile-collapse');
    if (open) box.open = true;
    const head = el('summary', 'profile-collapse__head');
    head.tabIndex = 0;
    head.append(el('span', 'profile-collapse__title', title), el('span', 'profile-collapse__count', String(count)));
    head.insertAdjacentHTML('beforeend', iconSvg('chevron-down', 'profile-collapse__chevron'));
    box.append(head, content);
    return box;
}

function scoreList(rows) {
    const list = el('ol', 'profile-records');
    rows.forEach((r) => {
        const li = el('li', 'profile-record');
        li.append(
            el('span', 'profile-record__name', r.name),
            el('span', 'profile-record__times', r.meta || ''),
            el('span', 'profile-record__best', pct(r.score)),
        );
        list.append(li);
    });
    return list;
}

// Perfil: foto e apelido em destaque, três números e a melhor música. "Ver mais"
// abre os detalhes em listas recolhíveis (recordes, partidas gravadas, últimas).
// opts: { name, editable, onChanged } — no celular, o próprio cantor põe a foto
// mesmo antes da primeira partida (sem `detail`).
export async function renderProfile(container, detail, opts = {}) {
    stopReplay();
    container.replaceChildren();
    if (!detail) {
        if (opts.name) container.append(renderHead(opts.name, await fetchAvatarVersion(opts.name), opts));
        container.append(el('p', 'profile-empty', 'Ainda sem partidas'));
        return;
    }
    container.append(renderHead(detail.name, detail.avatar, opts));

    const stats = el('div', 'profile-stats');
    stats.append(
        stat('músicas', String(detail.games), 'note'),
        stat('média', pct(detail.avg), 'gauge'),
        stat('recorde', pct(detail.best), 'trophy'),
    );
    container.append(stats);

    const records = detail.records || [];
    if (records.length) {
        const top = records[0];
        const best = el('div', 'profile-best');
        best.insertAdjacentHTML('beforeend', iconSvg('crown', 'profile-best__icon'));
        const text = el('span', 'profile-best__text');
        text.append(el('span', 'profile-best__label', 'Melhor música'), el('span', 'profile-best__song', top.name || top.song_id));
        best.append(text, el('span', 'profile-best__score', pct(top.best)));
        container.append(best);
    }

    const details = el('div', 'profile-details');
    details.hidden = true;
    if (typeof detail.avg_pitch === 'number') {
        const pitch = el('p', 'profile-pitch');
        pitch.insertAdjacentHTML('beforeend', iconSvg('pitch'));
        pitch.append(el('span', null, 'Afinação média'), el('strong', null, pct(detail.avg_pitch)));
        details.append(pitch);
    }
    if (records.length) {
        details.append(collapsible('Recordes', Math.min(records.length, 30), scoreList(records.slice(0, 30).map((r) => ({
            name: r.name || r.song_id, meta: r.times > 1 ? `${r.times}×` : '', score: r.best,
        })))));
    }
    // Partidas gravadas: tocar abre a análise verso a verso (a mesma do fim de jogo)
    const sessions = el('div', 'profile-sessions');
    details.append(sessions);
    renderSessions(sessions, detail.name);
    if (detail.recent && detail.recent.length) {
        details.append(collapsible('Últimas', detail.recent.length, scoreList(detail.recent.map((r) => ({
            name: r.name, meta: formatDate(r.date), score: r.score,
        })))));
    }

    const more = el('button', 'btn btn--ghost btn--block profile-more');
    more.type = 'button';
    more.setAttribute('aria-expanded', 'false');
    const paintMore = () => {
        more.innerHTML = iconSvg(details.hidden ? 'chevron-down' : 'chevron-up');
        more.append(el('span', null, details.hidden ? 'Ver mais' : 'Ver menos'));
    };
    paintMore();
    more.addEventListener('click', () => {
        details.hidden = !details.hidden;
        more.setAttribute('aria-expanded', String(!details.hidden));
        paintMore();
    });
    container.append(more, details);
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
    box.append(collapsible('Partidas gravadas', Math.min(games.length, 30), list));
}
