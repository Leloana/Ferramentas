// Tela final no celular: placar da sala, a média de quem cantou e os botões
// Cartão, Anotar meus versos e Ouvir.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { escapeHtml } from '../core/html.js';
import { openShareCard, splitSongTitle } from '../game/share-card.js';
import { toggleReplay } from '../audio/replay.js';
import { openAnnotationFor } from '../players/annotate.js';
import { COMBO_MIN } from '../game/combo.js';

// Nota final deste celular (a geral quando o servidor não manda por jogador)
function myFinalScore(data) {
    if (data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname] !== undefined) {
        return data.player_scores[state.mobileNickname];
    }
    return data.total_score;
}

function finalHtml(data, myTotalScore) {
    let html = `<div class="mic-final">`;
    html += `<span class="mic-final__title">Placar final</span>`;
    if (state.isActiveInGame) {
        html += `<span class="mic-final__avg">Sua média: <strong>${myTotalScore.toFixed(1)}%</strong></span>`;
        const mine = data.player_stats && data.player_stats[state.mobileNickname];
        if (mine && mine.best_combo >= COMBO_MIN) {
            html += `<span class="mic-final__combo">${iconSvg('flame')} Maior combo: <strong>×${mine.best_combo}</strong></span>`;
        }
    }
    if (data.player_scores && Object.keys(data.player_scores).length > 0) {
        html += `<div class="mic-final__list">`;
        const sortedPlayers = Object.entries(data.player_scores).sort((a, b) => b[1] - a[1]);
        sortedPlayers.forEach(([name, score], idx) => {
            const displayName = name === "PC_Local" ? "Local" : name;
            const isMe = name === state.mobileNickname;
            html += `<div class="mic-final__row${isMe ? ' mic-final__row--me' : ''}">`;
            html += `<span><span class="place-num">${idx + 1}º</span> ${escapeHtml(displayName)}</span>`;
            html += `<span>${score.toFixed(1)}%</span>`;
            html += `</div>`;
        });
        html += `</div>`;
    } else if (!state.isActiveInGame) {
        html += `<span class="mic-note">Placar na TV</span>`;
    }
    html += `</div>`;
    return html;
}

function actionButton(className, icon, label, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = className;
    btn.innerHTML = `${iconSvg(icon)} ${label}`;
    btn.addEventListener('click', () => onClick(btn));
    return btn;
}

// Cartão para print com a nota deste celular e, com a partida gravada, anotar e ouvir
function finalButtons(data, myTotalScore) {
    const me = state.mobileNickname;
    const song = splitSongTitle(data.song_title);
    const buttons = [actionButton('btn btn--primary btn--block btn-share-card', 'camera', 'Cartão', () => openShareCard({
        songId: data.song_id,
        title: song.title,
        artist: song.artist,
        score: myTotalScore,
        pitch: data.player_pitch ? data.player_pitch[me] : undefined,
        stats: data.player_stats ? data.player_stats[me] : null,
        name: me,
        record: data.records ? data.records[me] : null,
    }))];
    if (data.recording_id && data.player_stats && data.player_stats[me]) {
        // anotar os próprios versos (certo/errado/cantarolei): é o que permite
        // calibrar a nota com partidas reais
        buttons.push(actionButton('btn btn--block btn-replay', 'edit', 'Anotar meus versos',
            () => openAnnotationFor(data.recording_id, me)));
        buttons.push(actionButton('btn btn--block btn-replay', 'headphones', 'Ouvir', (btn) => toggleReplay({
            recordingId: data.recording_id, player: me, songId: data.song_id, button: btn,
        })));
    }
    return buttons;
}

export function showMicGameOver(data) {
    const scoreLine = document.getElementById('mobile-score-text');
    if (scoreLine) scoreLine.hidden = true;
    const lyrText = document.getElementById('mobile-lyrics-text');
    if (!lyrText) return;
    lyrText.classList.remove('lyrics-line');
    const myTotalScore = myFinalScore(data);
    lyrText.innerHTML = finalHtml(data, myTotalScore);
    if (state.isActiveInGame && state.mobileNickname) {
        const finalBox = lyrText.querySelector('.mic-final') || lyrText;
        finalButtons(data, myTotalScore).forEach((btn) => finalBox.append(btn));
    }
}
