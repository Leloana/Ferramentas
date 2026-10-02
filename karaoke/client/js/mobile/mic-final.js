// Tela final no celular: quem cantou vê o próprio cartão para print (com os
// quadradinhos de estilo) e os botões Anotar meus versos e Ouvir; quem só
// assistiu vê o placar da sala.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { escapeHtml } from '../core/html.js';
import { mountShareCard, splitSongTitle } from '../game/share-card.js';
import { toggleReplay } from '../audio/replay.js';
import { openAnnotationFor } from '../players/annotate.js';

// Nota final deste celular (a geral quando o servidor não manda por jogador)
function myFinalScore(data) {
    if (data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname] !== undefined) {
        return data.player_scores[state.mobileNickname];
    }
    return data.total_score;
}

// Placar da sala (para quem só assistiu)
function finalHtml(data) {
    let html = `<div class="mic-final">`;
    html += `<span class="mic-final__title">Placar final</span>`;
    if (data.player_scores && Object.keys(data.player_scores).length > 0) {
        html += `<div class="mic-final__list">`;
        const sortedPlayers = Object.entries(data.player_scores).sort((a, b) => b[1] - a[1]);
        sortedPlayers.forEach(([name, score], idx) => {
            const displayName = name === "PC_Local" ? "Local" : name;
            html += `<div class="mic-final__row">`;
            html += `<span><span class="place-num">${idx + 1}º</span> ${escapeHtml(displayName)}</span>`;
            html += `<span>${score.toFixed(1)}%</span>`;
            html += `</div>`;
        });
        html += `</div>`;
    } else {
        html += `<span class="mic-note">Placar na TV</span>`;
    }
    html += `</div>`;
    return html;
}

// Cartão de quem cantou, com a nota deste celular
function myCardData(data, myTotalScore) {
    const me = state.mobileNickname;
    const song = splitSongTitle(data.song_title);
    return {
        songId: data.song_id,
        title: song.title,
        artist: song.artist,
        score: myTotalScore,
        pitch: data.player_pitch ? data.player_pitch[me] : undefined,
        stats: data.player_stats ? data.player_stats[me] : null,
        name: me,
        record: data.records ? data.records[me] : null,
    };
}

function actionButton(className, icon, label, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = className;
    btn.innerHTML = `${iconSvg(icon)} ${label}`;
    btn.addEventListener('click', () => onClick(btn));
    return btn;
}

// Com a partida gravada: anotar os próprios versos e ouvir
function finalButtons(data) {
    const me = state.mobileNickname;
    const buttons = [];
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

const FINAL_CLASS = 'mobile-lyrics--final';

// O placar com os botões é mais alto que a caixa da letra (até 42vh): no fim a
// caixa cresce e alinha pelo topo. A partida seguinte volta ao tamanho da letra.
export function setFinalLayout(on) {
    const box = document.getElementById('mobile-lyrics-container');
    if (box) box.classList.toggle(FINAL_CLASS, on);
}

export function showMicGameOver(data) {
    const scoreLine = document.getElementById('mobile-score-text');
    if (scoreLine) scoreLine.hidden = true;
    const lyrText = document.getElementById('mobile-lyrics-text');
    if (!lyrText) return;
    lyrText.classList.remove('lyrics-line');
    setFinalLayout(true);
    if (!(state.isActiveInGame && state.mobileNickname)) {
        lyrText.innerHTML = finalHtml(data);
        return;
    }
    const finalBox = document.createElement('div');
    finalBox.className = 'mic-final mic-final--card';
    const share = document.createElement('div');
    share.className = 'mic-final__share';
    mountShareCard(share, myCardData(data, myFinalScore(data)));
    finalBox.append(share);
    finalButtons(data).forEach((btn) => finalBox.append(btn));
    lyrText.replaceChildren(finalBox);
}
