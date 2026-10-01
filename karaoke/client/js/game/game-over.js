// Fim de jogo na TV: nota e rank (solo) ou pódio (disputa), recordes, botões
// "Ouvir" e os dados do cartão para print.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { micLabel, groupName, PC_MIC } from '../lobby/lobby.js';
import { groupFinalScores } from './score-bars.js';
import { openShareCard, rankFor } from './share-card.js';
import { toggleReplay } from '../audio/replay.js';
import { escapeHtml } from '../core/html.js';
import { resetGameState } from './session.js';

const RANK_TITLES = {
    S: 'PERFORMANCE LENDÁRIA!',
    A: 'EXCELENTE APRESENTAÇÃO!',
    B: 'BOM TRABALHO!',
    C: 'PRECISA PRATICAR!',
};

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

// Times (duplas/trios): o pódio mostra a nota do time, média dos membros.
// Retorna { scores: {nome: nota}, members: {nome: "Ana 80% · Bia 70%"} }.
function podiumScores(playerScores) {
    const teamResults = playerScores ? groupFinalScores(playerScores) : null;
    if (!teamResults) return { scores: playerScores, members: {} };
    const scores = {};
    const members = {};
    teamResults.forEach((r) => {
        const name = teamLabel(r);
        scores[name] = r.score;
        if (r.members.length > 1) {
            members[name] = r.members.map((m) => `${micLabel(m.mic)} ${Math.round(m.score)}%`).join(' · ');
        }
    });
    return { scores, members };
}

function podiumColumn(entry, place, teamMembers) {
    const name = escapeHtml(micLabel(entry[0]));
    const members = teamMembers[entry[0]] ? `<span class="podium-members">${escapeHtml(teamMembers[entry[0]])}</span>` : '';
    const crown = place === 1 ? `<span class="podium-crown">${iconSvg('crown')}</span>` : '';
    const cls = { 1: 'podium-1st', 2: 'podium-2nd', 3: 'podium-3rd' }[place];
    return `
                <div class="podium-col ${cls}">
                    ${crown}
                    <span class="podium-name" title="${name}">${name}</span>
                    ${members}
                    <span class="podium-score">${entry[1].toFixed(1)}%</span>
                    <div class="podium-pedestal">${place}</div>
                </div>
            `;
}

// Pódio com 2º, 1º e 3º lado a lado e o 4º numa linha embaixo
function buildPodium(sortedPlayers, teamMembers) {
    const [first, second, third, fourth] = sortedPlayers;
    let columnsHtml = '';
    if (second) columnsHtml += podiumColumn(second, 2, teamMembers);
    if (first) columnsHtml += podiumColumn(first, 1, teamMembers);
    if (third) {
        columnsHtml += podiumColumn(third, 3, teamMembers);
    } else if (second) {
        // espaço vazio para o 1º ficar no centro com só dois no pódio
        columnsHtml += `<div class="podium-col podium-col--spacer"></div>`;
    }

    const podiumArea = document.createElement('div');
    podiumArea.id = 'podium-area';
    podiumArea.className = 'podium-container';
    podiumArea.innerHTML = `
            <div class="podium-columns">
                ${columnsHtml}
            </div>
            <div id="podium-extra-list" class="podium-extra-list"></div>
        `;
    if (fourth) {
        const item = document.createElement('div');
        item.className = 'podium-extra-item';
        item.innerHTML = `<span>4º Lugar: ${escapeHtml(micLabel(fourth[0]))}</span><span class="score-num">${fourth[1].toFixed(1)}%</span>`;
        podiumArea.querySelector('#podium-extra-list').appendChild(item);
    }
    return podiumArea;
}

// Lista de notas embaixo da nota geral (só com um único jogador)
function showBreakdown(modalScore, sortedPlayers, show) {
    let breakdownDiv = document.getElementById('modal-mp-breakdown');
    if (!breakdownDiv) {
        breakdownDiv = document.createElement('div');
        breakdownDiv.id = 'modal-mp-breakdown';
        breakdownDiv.className = 'mp-breakdown';
        modalScore.parentNode.appendChild(breakdownDiv);
    }
    breakdownDiv.innerHTML = '';
    breakdownDiv.hidden = !show;
    if (!show) return;
    sortedPlayers.forEach(([name, score], idx) => {
        const item = document.createElement('div');
        item.className = 'mp-breakdown__row';
        item.innerHTML = `<span><span class="place-num">${idx + 1}º</span> ${escapeHtml(micLabel(name))}</span><span>${score.toFixed(1)}%</span>`;
        breakdownDiv.appendChild(item);
    });
}

export function showGameOverModal(finalScore, rawPlayerScores) {
    const modal = document.getElementById('game-over-modal');
    const rankBadge = document.getElementById('rank-badge');
    const rankTitle = document.getElementById('rank-title');
    const modalScore = document.getElementById('modal-score');

    modalScore.innerText = finalScore.toFixed(1) + '%';

    // cor do rank vem do CSS (.rank-badge[data-rank])
    const rank = rankFor(finalScore).letter;
    rankBadge.innerText = rank;
    rankBadge.dataset.rank = rank;
    rankTitle.innerText = RANK_TITLES[rank];
    const rankSeal = rankBadge.parentNode;

    const { scores: playerScores, members: teamMembers } = podiumScores(rawPlayerScores);
    const sortedPlayers = playerScores ? Object.entries(playerScores).sort((a, b) => b[1] - a[1]) : [];
    const multiplayer = sortedPlayers.length > 1;

    const oldPodium = document.getElementById('podium-area');
    if (oldPodium) oldPodium.remove();

    // disputa: pódio no lugar do selo de rank, antes da caixa da nota
    rankSeal.hidden = multiplayer;
    rankTitle.hidden = multiplayer;
    if (multiplayer) {
        const scoreBox = modalScore.parentNode;
        scoreBox.parentNode.insertBefore(buildPodium(sortedPlayers, teamMembers), scoreBox);
    }

    showBreakdown(modalScore, sortedPlayers, !!playerScores && sortedPlayers.length > 0 && !multiplayer);

    modal.setAttribute('data-open', 'true');

    const shareBtn = document.getElementById('btn-share-card');
    if (shareBtn) {
        shareBtn.onclick = () => openShareCard(shareDataFromGameOver(state.lastGameOver || {
            total_score: finalScore, player_scores: playerScores || {},
        }));
    }

    document.getElementById('btn-restart-game').onclick = () => {
        resetGameState();
    };
}
