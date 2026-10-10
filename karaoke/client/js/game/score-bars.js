// Barras de placar nas bordas da TV durante a partida com mais de um microfone.
//
// Uma barra por time: 2 times ficam na esquerda e na direita (sobra altura para a
// letra); 3 ou 4, embaixo, no topo, na esquerda e na direita. Time com mais de
// um cantor (dupla/trio) mostra a nota do time em destaque — média dos membros —
// e, embaixo, uma barra discreta com a nota de cada membro.

import { state } from '../core/state.js';
import { micLabel, groupName } from '../lobby/lobby.js';
import { stampVerse, clearStamp, replayClass, verseQuality } from './verse-stamp.js';

const SLOTS = ['p1', 'p2', 'p3', 'p4'];
const TEAMS = ['A', 'B', 'C', 'D'];

// p1 baixo, p2 topo, p3 esquerda, p4 direita (partials/score-bars.html)
const SIDES_ONLY = ['p3', 'p4'];

// Barra do time `idx` da escalação em curso (state.scoreGroups)
export function barOf(idx) {
    const groups = state.scoreGroups || [];
    const slots = groups.length === 2 ? SIDES_ONLY : SLOTS;
    return slots[idx] ? document.getElementById(`mp-score-bar-${slots[idx]}`) : null;
}

function setFill(bar, selector, pct) {
    const fill = bar.querySelector(selector);
    if (!fill) return;
    if (fill.classList.contains('mp-progress-fill-vertical')) fill.style.height = pct + '%';
    else fill.style.width = pct + '%';
}

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

export function hideScoreBars() {
    SLOTS.forEach((key) => {
        const bar = document.getElementById(`mp-score-bar-${key}`);
        if (!bar) return;
        bar.removeAttribute('data-active');
        bar.classList.remove('mp-score-bar--good', 'mp-score-bar--ok', 'mp-score-bar--poor', 'mp-score-bar--team');
        const trans = bar.querySelector('.mp-player-transcription');
        if (trans) trans.replaceChildren();
        clearStamp(bar.querySelector('.verse-stamp'));
        const members = bar.querySelector('.mp-members');
        if (members) members.replaceChildren();
    });
}

// groups: [{ team: 'A', mics: ['Marcelo', 'Ana'] }, ...] (lobbyLineup)
export function showScoreBars(groups) {
    hideScoreBars();
    state.scoreGroups = groups;
    groups.slice(0, SLOTS.length).forEach((group, idx) => {
        const bar = barOf(idx);
        if (!bar) return;
        const isTeam = group.mics.length > 1;
        bar.setAttribute('data-active', 'true');
        bar.dataset.player = String(TEAMS.indexOf(group.team) + 1); // cor do time
        bar.classList.toggle('mp-score-bar--team', isTeam);
        bar.querySelector('.mp-player-name').textContent = isTeam
            ? `${groupName(group.mics.length)} ${group.team}`
            : micLabel(group.mics[0]);
        bar.querySelector('.mp-player-pct').textContent = '0%';
        if (!bar.querySelector('.verse-stamp')) {
            const stamp = el('div', 'verse-stamp verse-stamp--mini');
            stamp.append(el('span', 'verse-stamp__word'), el('span', 'verse-stamp__score'));
            bar.append(stamp);
        }
        setFill(bar, '.mp-progress-fill, .mp-progress-fill-vertical', 0);

        const members = bar.querySelector('.mp-members');
        if (!members) return;
        members.replaceChildren();
        if (!isTeam) return;
        group.mics.forEach((mic) => {
            const row = el('div', 'mp-member');
            row.dataset.mic = mic;
            const track = el('span', 'mp-member__track');
            track.append(el('span', 'mp-member__fill'));
            row.append(el('span', 'mp-member__name', micLabel(mic)), track, el('span', 'mp-member__pct', '0%'));
            members.append(row);
        });
    });
}

function qualityClass(score) {
    return `mp-score-bar--${verseQuality(score).key}`;
}

// playerScores: { microfone: { total_score, score, transcription } } do servidor.
// renderHeard(container, transcription, expected, showHeader) vem de game/transcription.js.
export function updateScoreBars(playerScores, expected, renderHeard, opts) {
    const recalc = !!(opts && opts.recalc);
    const groups = state.scoreGroups || [];
    if (state.mpBorderTimers) state.mpBorderTimers.forEach((t) => clearTimeout(t));
    state.mpBorderTimers = [];

    groups.slice(0, SLOTS.length).forEach((group, idx) => {
        const bar = barOf(idx);
        if (!bar) return;
        const results = group.mics.map((mic) => playerScores[mic] || {});
        const avg = (key) => results.reduce((sum, r) => sum + (r[key] || 0), 0) / Math.max(1, results.length);
        const total = avg('total_score');

        bar.querySelector('.mp-player-pct').textContent = total.toFixed(1) + '%';
        setFill(bar, '.mp-progress-fill, .mp-progress-fill-vertical', total);

        group.mics.forEach((mic, i) => {
            const row = bar.querySelector(`.mp-member[data-mic="${CSS.escape ? CSS.escape(mic) : mic}"]`);
            if (!row) return;
            const value = results[i].total_score || 0;
            row.querySelector('.mp-member__pct').textContent = Math.round(value) + '%';
            row.querySelector('.mp-member__fill').style.width = value + '%';
        });

        if (recalc) return;  // voltou a música: só os totais

        const verseScore = avg('score');
        bar.classList.remove('mp-score-bar--good', 'mp-score-bar--ok', 'mp-score-bar--poor');
        bar.classList.add(qualityClass(verseScore));
        replayClass(bar, 'mp-score-bar--flash');
        stampVerse(bar.querySelector('.verse-stamp'), verseScore);

        // "Ouvi": uma linha por membro quando é time
        const trans = bar.querySelector('.mp-player-transcription');
        if (trans) {
            if (group.mics.length === 1) {
                renderHeard(trans, results[0].transcription || '', expected, true, results[0].heard_hits);
            } else {
                trans.replaceChildren();
                group.mics.forEach((mic, i) => {
                    const line = el('div', 'heard-line');
                    const who = el('strong', null, `${micLabel(mic)}: `);
                    const words = el('span');
                    renderHeard(words, results[i].transcription || '', expected, false, results[i].heard_hits);
                    line.append(who, words);
                    trans.append(line);
                });
            }
        }
    });

    // Moldura de desempenho e "Ouvi" somem depois de 2 s
    state.mpBorderTimers.push(setTimeout(() => {
        SLOTS.forEach((key) => {
            const bar = document.getElementById(`mp-score-bar-${key}`);
            if (!bar) return;
            bar.classList.remove('mp-score-bar--good', 'mp-score-bar--ok', 'mp-score-bar--poor');
            const trans = bar.querySelector('.mp-player-transcription');
            if (trans) trans.replaceChildren();
        });
    }, 2000));
}

// Para o pódio: nota final de cada time (média dos membros).
export function groupFinalScores(finalScores) {
    const groups = state.scoreGroups || [];
    if (!groups.some((g) => g.mics.length > 1)) return null;
    return groups.map((g) => {
        const values = g.mics.map((m) => finalScores[m] || 0);
        return {
            group: g,
            score: values.reduce((a, b) => a + b, 0) / Math.max(1, values.length),
            members: g.mics.map((m, i) => ({ mic: m, score: values[i] })),
        };
    }).sort((a, b) => b.score - a.score);
}
