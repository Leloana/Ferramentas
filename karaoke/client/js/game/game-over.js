// Fim de jogo na TV: o cartão para print é o placar (nota e rank, ou pódio na
// disputa), com recordes, botões "Ouvir" e "Cantar novamente" embaixo.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { micLabel, groupName, PC_MIC } from '../lobby/lobby.js';
import { groupFinalScores } from './score-bars.js';
import { mountShareCard } from './share-card.js';
import { toggleReplay } from '../audio/replay.js';
import { resetGameState } from './session.js';
import { COMBO_MIN } from './combo.js';

const MAX_REPLAY_BUTTONS = 4;

// Nome de um time no placar: "Dupla A" ou o apelido de quem cantou sozinho
function teamLabel(result) {
    return result.members.length > 1 ? `${groupName(result.members.length)} ${result.group.team}` : micLabel(result.members[0].mic);
}

// Chave de um jogador nas notas do servidor ("Solo" quando não há escalação)
function soloKey(data) {
    const keys = Object.keys(data.player_stats || {});
    return keys.length === 1 ? keys[0] : null;
}

// Botões "ouvir" (um por cantor com voz gravada)
function showReplayButtons(data) {
    const box = document.getElementById('game-over-replay');
    if (!box) return;
    box.replaceChildren();
    const players = Object.keys(data.player_stats || {});
    if (!data.recording_id || !players.length) {
        box.hidden = true;
        return;
    }
    players.slice(0, MAX_REPLAY_BUTTONS).forEach((player) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn--ghost btn-replay';
        const label = players.length > 1 ? `Ouvir ${micLabel(player)}` : 'Ouvir a apresentação';
        btn.innerHTML = `${iconSvg('headphones')}<span></span>`;
        btn.querySelector('span').textContent = label;
        btn.addEventListener('click', () => toggleReplay({
            recordingId: data.recording_id,
            player,
            songId: data.song_id || state.selectedSongId,
            button: btn,
        }));
        box.append(btn);
    });
    box.hidden = false;
}

// Recorde pessoal / melhor da sala abaixo da nota do fim de jogo
export function showGameOverExtras(data) {
    showReplayButtons(data);
    const box = document.getElementById('game-over-record');
    if (!box) return;
    const lines = [];
    const records = data.records || {};
    Object.keys(records).forEach((name) => {
        const r = records[name];
        if (r && r.is_record && r.times_sung > 1) lines.push(`Recorde pessoal de ${micLabel(name)}`);
    });
    // maior combo da partida: o melhor entre os cantores, a partir de 2 seguidos
    const stats = data.player_stats || {};
    const top = Object.keys(stats).reduce((best, name) => {
        const n = (stats[name] && stats[name].best_combo) || 0;
        return n > best.n ? { name, n } : best;
    }, { name: null, n: 0 });
    if (top.n >= COMBO_MIN) {
        const who = Object.keys(stats).length > 1 ? ` de ${micLabel(top.name)}` : '';
        lines.push(`Maior combo${who}: ×${top.n}`);
    }
    const board = data.leaderboard || [];
    if (board.length) lines.push(`Melhor da sala: ${board[0].name} · ${Math.round(board[0].best)}%`);
    box.textContent = lines.join('  ·  ');
    box.hidden = !lines.length;
}

// Monta os dados do cartão para print a partir do game_over.
function shareDataFromGameOver(data) {
    const title = document.getElementById('current-song-title');
    const artist = document.getElementById('current-song-artist');
    const scores = data.player_scores || {};
    const names = Object.keys(scores);
    const key = soloKey(data);
    const teams = groupFinalScores(scores);
    let podium = null;
    if (teams && teams.length > 1) {
        podium = teams.map((t) => ({ name: teamLabel(t), score: t.score }));
    } else if (names.length > 1) {
        podium = names.map((n) => ({ name: micLabel(n), score: scores[n] })).sort((a, b) => b.score - a.score);
    }
    const pitchValues = Object.keys(data.player_pitch || {}).map((k) => data.player_pitch[k]);
    const one = key && key !== 'Solo' && key !== PC_MIC ? key : null;
    return {
        songId: data.song_id || state.selectedSongId,
        title: title ? title.textContent : '',
        artist: artist ? artist.textContent : '',
        score: podium ? podium[0].score : (parseFloat(data.total_score) || 0),
        pitch: key && data.player_pitch && typeof data.player_pitch[key] === 'number'
            ? data.player_pitch[key]
            : (pitchValues.length === 1 ? pitchValues[0] : undefined),
        stats: key ? data.player_stats[key] : null,
        name: one,
        record: one && data.records ? data.records[one] : null,
        podium,
    };
}

export function showGameOverModal(data) {
    const modal = document.getElementById('game-over-modal');
    mountShareCard(document.getElementById('game-over-share'), shareDataFromGameOver(data));
    modal.setAttribute('data-open', 'true');

    document.getElementById('btn-restart-game').onclick = () => {
        resetGameState();
    };
}
