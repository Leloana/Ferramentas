// Fim de jogo na TV: o cartão para print é o placar — um por cantor, da maior
// nota para a menor — com recordes e "Cantar novamente" embaixo. Ouvir a própria
// voz fica no celular de cada um (mobile/mic-final.js).
import { state } from '../core/state.js';
import { micLabel, PC_MIC } from '../lobby/lobby.js';
import { mountShareCards } from './share-card.js';
import { resetGameState } from './session.js';
import { COMBO_MIN } from './combo.js';

// Chave de um jogador nas notas do servidor ("Solo" quando não há escalação)
function soloKey(data) {
    const keys = Object.keys(data.player_stats || {});
    return keys.length === 1 ? keys[0] : null;
}

// Recorde pessoal / melhor da sala abaixo da nota do fim de jogo
export function showGameOverExtras(data) {
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

// Cartão de um cantor (`key` como o servidor manda: apelido, PC_MIC ou "Solo")
function playerCard(data, key, score) {
    const title = document.getElementById('current-song-title');
    const artist = document.getElementById('current-song-artist');
    const named = key && key !== 'Solo' ? key : null;
    const pitch = key && data.player_pitch ? data.player_pitch[key] : undefined;
    return {
        songId: data.song_id || state.selectedSongId,
        title: title ? title.textContent : '',
        artist: artist ? artist.textContent : '',
        score,
        pitch: typeof pitch === 'number' ? pitch : undefined,
        stats: key && data.player_stats ? data.player_stats[key] || null : null,
        name: named ? micLabel(named) : null,
        record: named && named !== PC_MIC && data.records ? data.records[named] : null,
    };
}

// Cartões do game_over: um por cantor, da maior nota para a menor
function shareCardsFromGameOver(data) {
    const scores = data.player_scores || {};
    const names = Object.keys(scores);
    if (names.length > 1) {
        return names
            .sort((a, b) => scores[b] - scores[a])
            .map((name) => playerCard(data, name, scores[name]));
    }
    const key = soloKey(data) || names[0] || null;
    const card = playerCard(data, key, parseFloat(data.total_score) || 0);
    const pitchValues = Object.keys(data.player_pitch || {}).map((k) => data.player_pitch[k]);
    if (card.pitch === undefined && pitchValues.length === 1) card.pitch = pitchValues[0];
    if (key === PC_MIC) card.name = null;  // cantou sozinho no PC: sem "cantado por Local"
    return [card];
}

export function showGameOverModal(data) {
    const modal = document.getElementById('game-over-modal');
    mountShareCards(document.getElementById('game-over-share'), shareCardsFromGameOver(data));
    modal.setAttribute('data-open', 'true');

    document.getElementById('btn-restart-game').onclick = () => {
        resetGameState();
    };
}
