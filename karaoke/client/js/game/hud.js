// Placar da TV durante a partida: nota do verso, nota geral, moldura de
// desempenho, selo "Vez de ..." e as barras de progresso do verso e do solo.
import { state } from '../core/state.js';
import { groupName, micLabel } from '../lobby/lobby.js';
import { showScoreBars, hideScoreBars, updateScoreBars, barOf } from './score-bars.js';
import { stampVerse, clearStamp, verseQuality, replayClass } from './verse-stamp.js';
import { renderTranscriptionInto, expectedWords } from './transcription.js';
import { clearCombos } from './combo.js';
import { clearReactions } from './reactions.js';

const PERF_BORDER_MS = 2000;

const byId = (id) => document.getElementById(id);

function isMultiplayer() {
    return !!(state.activePlayers && state.activePlayers.length > 1);
}

// Nota geral (lateral). No recálculo (voltou a música) também atualiza as
// barras do multiplayer, só os números.
export function applyTotals(data) {
    const pitchEl = byId('pitch-avg-text');
    if (pitchEl && typeof data.pitch_avg === 'number') {
        pitchEl.textContent = `Tom ${Math.round(data.pitch_avg)}%`;
        pitchEl.hidden = false;
    }
    const val = parseFloat(data.total_score) || 0;
    const scoreFill = byId('score-progress-fill');
    if (scoreFill) scoreFill.style.height = val + '%';
    byId('score-percentage-text').innerText = val.toFixed(1) + '%';
    if (data.recalc && data.player_scores && isMultiplayer()) {
        updateScoreBars(data.player_scores, [], renderTranscriptionInto, { recalc: true });
    }
}

// Nota do verso que acabou: número, carimbo e moldura no solo, barras no multiplayer.
export function showVerseScore(data) {
    const segScore = byId('seg-score');
    segScore.innerText = data.score + '%';
    segScore.dataset.quality = verseQuality(data.score).key;
    replayClass(segScore, 'seg-score--pulse');
    // carimbo no palco só no solo; em disputa cada barra tem o seu
    if (!isMultiplayer()) {
        stampVerse(byId('verse-stamp'), data.score, 0, data.pitch);
    }
}

// Moldura colorida pela nota do último verso. Em disputa a nota geral mistura
// os times: a moldura fica só no solo.
export function flashPerfBorder(score) {
    const perfBorder = isMultiplayer() ? null : byId('perf-border-overlay');
    if (!perfBorder) return;
    perfBorder.className = `perf-border-${verseQuality(parseFloat(score) || 0).key}`;
    if (state.perfBorderTimer) clearTimeout(state.perfBorderTimer);
    state.perfBorderTimer = setTimeout(() => {
        perfBorder.className = 'perf-border-idle';
        state.perfBorderTimer = null;
    }, PERF_BORDER_MS);
}

export function updatePlayerBars(data) {
    if (!data.player_scores || !isMultiplayer()) return;
    // Barra por time + barrinha de cada membro (score-bars.js)
    updateScoreBars(data.player_scores, expectedWords(state.lastSegmentLyricsTimed), renderTranscriptionInto);
}

// Revezar versos: selo "Vez de ..." no palco e destaque da barra do time da vez
export function showTurn(owner) {
    const badge = byId('turn-badge');
    if (!badge) return;
    if (!owner) {
        badge.hidden = true;
        document.querySelectorAll('.mp-score-bar').forEach((b) => b.classList.remove('mp-score-bar--turn', 'mp-score-bar--waiting'));
        return;
    }
    const groups = state.scoreGroups || [];
    const gi = groups.findIndex((g) => g.mics.join('|') === owner.join('|'));
    const group = groups[gi];
    badge.textContent = `Vez de ${group && group.mics.length > 1 ? `${groupName(group.mics.length)} ${group.team}` : owner.map(micLabel).join(' + ')}`;
    badge.dataset.player = String(gi >= 0 ? (['A', 'B', 'C', 'D'].indexOf(group.team) + 1) : 1);
    badge.hidden = false;
    replayClass(badge, 'turn-badge--in');
    groups.forEach((g, i) => {
        const bar = barOf(i);
        if (!bar) return;
        bar.classList.toggle('mp-score-bar--turn', i === gi);
        bar.classList.toggle('mp-score-bar--waiting', i !== gi);
    });
}

// Contagem antes de voltar a cantar (n = 3, 2, 1; null esconde).
export function setCountdown(n) {
    const el = byId('verse-countdown');
    if (!el) return;
    if (n === null) {
        if (!el.hidden) el.hidden = true;
        el.dataset.n = '';
        return;
    }
    if (el.dataset.n === String(n)) return;
    el.dataset.n = String(n);
    el.textContent = String(n);
    el.hidden = false;
    replayClass(el, 'verse-countdown--tick');
}

export function setSilence(active) {
    const app = byId('app');
    if (!app) return;
    if (active) app.setAttribute('data-silence', 'true');
    else app.removeAttribute('data-silence');
}

export function setSilenceProgress(pct, remainingSec) {
    const fill = byId('silence-progress-fill');
    const text = byId('silence-timer-text');
    if (fill) fill.style.width = pct + '%';
    if (text) text.innerText = remainingSec.toFixed(1) + 's';
}

// Barrinha de progresso do verso atual
export function setVerseProgress(virtualTime, segStart, segEnd) {
    const container = byId('verse-progress-container');
    const fill = byId('verse-progress-fill');
    if (!container || !fill) return;
    const duration = segEnd - segStart;
    if (virtualTime >= segStart && virtualTime <= segEnd && duration > 0) {
        const pct = Math.max(0, Math.min(100, ((virtualTime - segStart) / duration) * 100));
        fill.style.width = pct + '%';
        container.setAttribute('data-active', 'true');
    } else if (virtualTime > segEnd) {
        fill.style.width = '100%';
        container.setAttribute('data-active', 'ended');
    } else {
        fill.style.width = '0%';
        container.removeAttribute('data-active');
    }
}

export function setOutroProgress(pct, remainingSec) {
    const fill = byId('outro-progress-fill');
    if (fill) fill.style.width = pct + '%';
    const text = byId('outro-timer-text');
    if (text) text.innerText = `Finalizando em ${remainingSec.toFixed(1)}s...`;
}

// Escalação com mais de um time: barras nas bordas. data-players/-count fazem o
// states.css esconder o placar solo e reservar espaço.
export function setPlayersLayout(lineup) {
    const app = byId('app');
    if (lineup.mics.length > 1) {
        showScoreBars(lineup.groups);
        app.setAttribute('data-players', 'multi');
        app.setAttribute('data-player-count', String(Math.min(4, lineup.groups.length)));
        if (lineup.mode === 'teams') app.setAttribute('data-teams', '');
        else app.removeAttribute('data-teams');
    } else {
        hideScoreBars();
    }
}

// Volta o placar ao estado de antes da partida
export function resetHud() {
    byId('seg-score').innerText = '0%';
    const statsSyncVal = byId('stats-sync-value');
    if (statsSyncVal) statsSyncVal.innerText = '0ms';

    const scoreFill = byId('score-progress-fill');
    if (scoreFill) {
        scoreFill.style.height = '0%';
        scoreFill.style.width = '';
    }
    byId('score-percentage-text').innerText = '0%';
    const pitchAvg = byId('pitch-avg-text');
    if (pitchAvg) pitchAvg.hidden = true;

    const perfBorder = byId('perf-border-overlay');
    if (perfBorder) perfBorder.className = 'perf-border-idle';
    clearStamp(byId('verse-stamp'));
    const segScore = byId('seg-score');
    if (segScore) delete segScore.dataset.quality;

    const verseContainer = byId('verse-progress-container');
    const verseFill = byId('verse-progress-fill');
    if (verseContainer && verseFill) {
        verseFill.style.width = '0%';
        verseContainer.removeAttribute('data-active');
    }

    const app = byId('app');
    if (app) {
        app.removeAttribute('data-silence');
        app.removeAttribute('data-players');
        app.removeAttribute('data-player-count');
        app.removeAttribute('data-teams');
    }

    if (state.mpBorderTimers) {
        state.mpBorderTimers.forEach(t => clearTimeout(t));
        state.mpBorderTimers = null;
    }
    if (state.perfBorderTimer) {
        clearTimeout(state.perfBorderTimer);
        state.perfBorderTimer = null;
    }

    byId('silence-progress-fill').style.width = '0%';
    hideScoreBars();
    clearCombos();
    clearReactions();
}
