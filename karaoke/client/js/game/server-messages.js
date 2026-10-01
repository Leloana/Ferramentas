// Mensagens do servidor para a TV (WebSocket role=display), uma função por tipo.
import { state, setAppState } from '../core/state.js';
import { dom } from '../core/dom.js';
import { setAvailableMics } from '../lobby/lobby.js';
import { onRequestsUpdate, showNextUp } from '../lobby/requests.js';
import { showToast } from '../core/toast.js';
import { updateMicStatusPanel } from '../audio/mic-status.js';
import { showAnnotationButton } from '../players/annotate.js';
import { renderLyrics } from './lyrics-carousel.js';
import { startHighlightLoop } from './highlight-loop.js';
import { showHeardHint, showHeardResult, listeningHint, expectedWords } from './transcription.js';
import { applyTotals, showVerseScore, flashPerfBorder, updatePlayerBars } from './hud.js';
import { showGameOverModal, showGameOverExtras } from './game-over.js';
import { resetGameState } from './session.js';
import { showReaction } from './reactions.js';
import { comboValue, showStageCombo, showBarCombos } from './combo.js';

function setPairingStatus(paired) {
    state.isMobileMicrophoneConnected = paired;
    updateMicStatusPanel();
    const text = document.getElementById('pairing-status-text');
    if (text) text.innerText = paired ? 'Celular conectado com sucesso!' : 'Aguardando conexão do celular...';
    const box = document.getElementById('pairing-status-box');
    if (box) {
        if (paired) box.setAttribute('data-status', 'paired');
        else box.removeAttribute('data-status');
    }
    if (paired) showToast("Microfone sem fio pareado e ativo!", "success");
    else showToast("Microfone sem fio desconectado.", "error");
}

// Combo: um cantor só no selo do palco, disputa nas barras.
// quiet: recálculo depois de voltar a música, sem animar.
function showCombos(data, quiet) {
    const scores = data.player_scores || {};
    if (state.activePlayers && state.activePlayers.length > 1) {
        showBarCombos(scores);
        return;
    }
    const keys = Object.keys(scores);
    showStageCombo(keys.length === 1 ? comboValue(scores[keys[0]]) : comboValue(data), quiet);
}

const DISPLAY_HANDLERS = {
    start_blocked(data) {
        // mutex de GPU no servidor: outra tela/aba tentou começar enquanto gera letra
        showToast(`${data.reason}. Aguarde terminar para começar.`, 'error');
        resetGameState();
    },
    requests_update(data) {
        onRequestsUpdate(data.requests);
    },
    request_error(data) {
        showToast(data.message, 'error');
    },
    players_update(data) {
        if (dom.mpConnectedCount) dom.mpConnectedCount.innerText = data.players.length;
        if (dom.mpQueueCount) dom.mpQueueCount.innerText = data.queue_count;
        // Microfones disponíveis para as vagas do lobby
        setAvailableMics(data.players);
    },
    pairing_status(data) {
        if (data.status === 'paired') setPairingStatus(true);
        else if (data.status === 'unpaired') setPairingStatus(false);
    },
    // Os três abaixo só valem sem a letra local (segments.json): com ela o laço
    // da letra decide sozinho quando se canta e quando troca o verso.
    singing_state(data) {
        if (state.currentSegments) return;
        state.isSingingActive = data.active;
        showHeardHint(listeningHint());
    },
    segment_start(data) {
        if (state.currentSegments) return;
        showHeardHint('[Solo Instrumental...]');
        renderLyrics(data);
        startHighlightLoop();
    },
    outro_start() {
        state.isOutroActive = true;
        state.outroStartPlayerTime = dom.audioPlayer.currentTime;
        state.outroTotalDuration = Math.max(1, dom.audioPlayer.duration - state.outroStartPlayerTime);
        setAppState('scoring');
        showHeardHint('[Show finalizado!]', true);
    },
    segment_result(data) {
        // Recálculo após voltar a música: só atualiza os totais, sem nota de verso
        if (data.recalc) {
            applyTotals(data);
            showCombos(data, true);
            return;
        }
        showVerseScore(data);
        showHeardResult(data.transcription, expectedWords(state.lastSegmentLyricsTimed), data.heard_hits);
        applyTotals(data);
        flashPerfBorder(data.score);
        updatePlayerBars(data);
        showCombos(data, false);
    },
    reaction(data) {
        showReaction(data.kind, data.from);
    },
    game_over(data) {
        dom.audioPlayer.pause();
        setAppState('game-over');
        state.lastGameOver = data;
        showGameOverModal(parseFloat(data.total_score) || 0, data.player_scores);
        showGameOverExtras(data);
        showNextUp();
        showAnnotationButton(data.recording_id);
    }
};

export function handleServerMessage(data) {
    const handler = DISPLAY_HANDLERS[data.type];
    if (handler) {
        handler(data);
    } else {
        console.warn(`Tipo de mensagem de display desconhecido recebido: ${data.type}`);
    }
}
