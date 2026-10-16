// Fim de jogo na TV: o cartão para print é o placar — um por cantor, da maior
// nota para a menor. Com um cantor e tela larga o cartão fica grande no meio, com
// os destaques (combo, melhor da sala, recorde) à esquerda e "Cantar novamente",
// a próxima da fila e os estilos à direita (game-over-card[data-cards="1"]).
// Com vários, os destaques vão dentro de cada cartão. Ouvir a própria voz fica no
// celular de cada um (mobile/mic-final.js).
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

function isMulti(data) {
    return Object.keys(data.player_scores || {}).length > 1;
}

function bestCombo(data, name) {
    const s = data.player_stats && data.player_stats[name];
    return (s && s.best_combo) || 0;
}

function roomBestText(data) {
    const board = data.leaderboard || [];
    return board.length ? `${board[0].name} · ${Math.round(board[0].best)}%` : null;
}

// Destaques dentro do cartão de um cantor (só com vários: com um, ficam ao lado)
function cardExtras(data, name) {
    const extras = [];
    const combo = bestCombo(data, name);
    if (combo >= COMBO_MIN) extras.push({ label: 'Combo', value: `×${combo}` });
    const best = roomBestText(data);
    if (best) extras.push({ label: 'Melhor da sala', value: best });
    return extras;
}

function statTile(label, value) {
    const tile = document.createElement('div');
    tile.className = 'game-over-stat';
    const l = document.createElement('span');
    l.className = 'game-over-stat__label';
    l.textContent = label;
    const v = document.createElement('strong');
    v.className = 'game-over-stat__value';
    v.textContent = value;
    tile.append(l, v);
    return tile;
}

// Destaques de quem cantou sozinho: ao lado do cartão (tela larga) ou embaixo dele
export function showGameOverExtras(data) {
    const box = document.getElementById('game-over-record');
    if (!box) return;
    const tiles = [];
    if (!isMulti(data)) {
        const records = data.records || {};
        Object.keys(records).forEach((name) => {
            const r = records[name];
            if (!r || !r.is_record || !(r.times_sung > 1)) return;
            const before = typeof r.best_before === 'number' ? `antes ${Math.round(r.best_before)}%` : micLabel(name);
            tiles.push(statTile('Recorde pessoal', before));
        });
        const key = soloKey(data);
        const combo = key ? bestCombo(data, key) : 0;
        if (combo >= COMBO_MIN) tiles.push(statTile('Maior combo', `×${combo}`));
        const best = roomBestText(data);
        if (best) tiles.push(statTile('Melhor da sala', best));
    }
    box.replaceChildren(...tiles);
    box.hidden = !tiles.length;
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
            .map((name) => {
                const card = playerCard(data, name, scores[name]);
                card.extras = cardExtras(data, name);
                return card;
            });
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
    const cards = shareCardsFromGameOver(data);
    modal.querySelector('.game-over-card').dataset.cards = String(cards.length);
    mountShareCards(document.getElementById('game-over-share'), cards, document.getElementById('game-over-styles'));
    modal.setAttribute('data-open', 'true');

    document.getElementById('btn-restart-game').onclick = () => {
        resetGameState();
    };
}
