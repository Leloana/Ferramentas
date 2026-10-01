// Ciclo de vida da partida na TV: carrega a letra, liga o áudio, abre o
// WebSocket do jogo (com reconexão no meio da música) e desmonta tudo no fim.
import { state, setAppState } from '../state.js';
import { dom } from '../dom.js';
import { myRoom, DISPLAY_REPLACED_CODE, isTvBrowser } from '../config.js';
import { lobbyLineup, validateLobby, PC_MIC } from '../lobby.js';
import { keepScreenOn, allowScreenOff } from '../wake-lock.js';
import { attachGuideSync, savedGuideVolume } from '../guide-vocal.js';
import { stopReplay } from '../replay.js';
import { stopAutoNext } from '../requests.js';
import { attachPlayerEvents, deviceInfo } from '../game-events.js';
import { showToast } from '../toast.js';
import { AudioLifecycleManager } from '../audio-lifecycle-manager.js';
import { updateSyncDisplay, startTimeSync, stopTimeSync } from '../sync.js';
import { updateMicStatusPanel } from '../mic-status.js';
import { connectDisplayWebSocket } from '../ws-display.js';
import { showAnnotationButton } from '../annotate.js';
import { handleServerMessage } from './server-messages.js';
import { startHighlightLoop, cancelLyricsFrame } from './highlight-loop.js';
import { resetCarousel } from './lyrics-carousel.js';
import { showHeardHint, clearHeardTimer } from './transcription.js';
import { showTurn, setPlayersLayout, resetHud } from './hud.js';
import { currentScoringMode, resetControls } from './controls.js';

const MAX_RECONNECT_ATTEMPTS = 5;

// Envia JSON pelo WebSocket da sala, se ele estiver aberto
export function sendToRoom(message) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(message));
    }
}

function closeRoomSocket() {
    if (!state.ws) return;
    try {
        state.ws.onclose = null;
        state.ws.close();
    } catch (e) { }
    state.ws = null;
}

// Copia os nós do AudioLifecycleManager para o state (sync, jungle, guia)
function adoptAudioNodes(manager) {
    state.audioContext = manager.audioContext;
    state.localStream = manager.localStream || null;
    state.micSourceNode = manager.micSourceNode || null;
    state.micProcessorNode = manager.micProcessorNode || null;
    state.mediaElementSource = manager.mediaElementSource;
    state.jungleNode = manager.jungleNode;
}

// streamMic: manda o áudio do microfone deste aparelho pelo WebSocket do jogo
async function startAudio(captureMic, streamMic) {
    const options = {
        captureMic,
        mediaElement: dom.audioPlayer,
        guideElement: dom.guidePlayer,
        guideVolume: savedGuideVolume(),
        nativePlayback: isTvBrowser,
    };
    if (streamMic) {
        // Música inteira, não só os versos (ver mobile-mic-view.js). Fora do
        // jogo o servidor descarta: sem relógio da música não há onde encaixar.
        options.onAudioChunk = (data) => {
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(data);
            }
        };
    }
    state.audioManager = new AudioLifecycleManager(options);
    state.audioManager.currentTranspose = state.currentTranspose;
    await state.audioManager.init();
    await state.audioManager.start();
    adoptAudioNodes(state.audioManager);
}

async function destroyAudio() {
    if (state.audioManager) {
        await state.audioManager.destroy();
        state.audioManager = null;
    }
}

export async function resetGameState() {
    const gameOverModal = document.getElementById('game-over-modal');
    if (gameOverModal) gameOverModal.removeAttribute('data-open');
    showAnnotationButton(null);

    if (state.slideTransitionCleanup) {
        state.slideTransitionCleanup();
    }
    clearHeardTimer();
    // invalida um startKaraoke/reconexão ainda em andamento
    state.gameGeneration++;
    if (state.gameReconnectTimer) {
        clearTimeout(state.gameReconnectTimer);
        state.gameReconnectTimer = null;
    }
    stopTimeSync();
    allowScreenOff();
    stopReplay();
    stopAutoNext();
    showTurn(null);
    state.turnOrder = null;
    closeRoomSocket();
    await destroyAudio();
    resetControls();
    state.localStream = null;
    state.micProcessorNode = null;
    state.micSourceNode = null;
    state.audioContext = null;
    state.mediaElementSource = null;
    state.jungleNode = null;

    cancelLyricsFrame();
    setAppState('idle');

    state.isSingingActive = false;
    state.isOutroActive = false;
    dom.audioPlayer.pause();
    dom.audioPlayer.src = '';

    showHeardHint('[Aguardando canto...]', true);
    resetHud();
    resetCarousel();

    state.selectedSongId = null;
    state.currentSegments = null;
    state.currentSegmentData = null;
    state.lastSegmentLyricsTimed = null;
    state.syncOffset = 0;
    state.isFirstSegment = true;
    state.totalPauseDuration = 0;
    state.activePlayers = null;
    state.gameMode = null;
    updateSyncDisplay();

    connectDisplayWebSocket();
}

// Carrega o segments.json inteiro antes de iniciar: a TV troca de verso sozinha
async function loadSegments(songId) {
    try {
        const resp = await fetch(`/api/songs/${songId}`);
        if (!resp.ok) throw new Error("Falha ao carregar os segmentos da música");
        const songData = await resp.json();
        state.currentSegments = songData.segments;
        console.log(`Carregados ${state.currentSegments.length} segmentos para a música localmente.`);
    } catch (err) {
        console.error("Erro ao pré-carregar os segmentos:", err);
        // main.js mostra o erro e libera o botão INICIAR
        throw new Error("não foi possível carregar a música");
    }
}

// Liga a música e, se for o caso, o microfone deste aparelho. Sem microfone,
// segue só com a música.
async function startGameAudio(captureMic) {
    await destroyAudio();
    try {
        await startAudio(captureMic, true);
        if (state.localStream) {
            // TV Bro não guarda a permissão: o painel só sabe do microfone depois do aviso
            state.localStreamForced = true;
            updateMicStatusPanel();
        }
    } catch (err) {
        if (!captureMic) throw err;
        console.warn("Sem microfone local detectado. Continuando apenas para reprodução...", err);
        if (!state.isMobileMicrophoneConnected) {
            showToast("Modo som de fundo ativo (sem microfone local)", "warning");
        }
        await destroyAudio();
        await startAudio(false, false);
    }
}

function startGameMessage(game) {
    return {
        type: "start_game",
        game_mode: game.lineup.mode,
        active_players: game.lineup.mics,
        scoring_mode: game.scoringMode,
        transpose: state.currentTranspose || 0,
        turns: !!state.turnOrder,
        turn_order: state.turnOrder || undefined,
        // contexto para a gravação completa (server/recorder.py)
        settings: {
            groups: game.lineup.groups,
            speed: state.currentSpeed,
            sync_offset: state.syncOffset,
            backing_volume: state.audioManager ? state.audioManager.currentVolume : null,
            guide_volume: savedGuideVolume(),
            display: { user_agent: navigator.userAgent, tv: document.documentElement.classList.contains('is-tv') },
        }
    };
}

// WebSocket do jogo. Reconexão no meio da música: o servidor mantém placar e
// gravação (resume=1) e o front não reinicia a música nem a tela.
function connectGameWebSocket(game, attempt) {
    state.gameReconnectTimer = null;
    if (game.cancelled()) return;
    const resuming = attempt > 0;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${encodeURIComponent(myRoom)}?role=display&song_id=${encodeURIComponent(game.songId)}${resuming ? '&resume=1' : ''}`;
    const ws = new WebSocket(wsUrl);
    state.ws = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        attempt = 0;
        ws.send(JSON.stringify({ type: "client_info", sample_rate: game.sampleRate, ...deviceInfo(state.localStream) }));
        if (resuming) {
            startTimeSync();
            return;
        }
        ws.send(JSON.stringify(startGameMessage(game)));
        state.isFirstSegment = true;
        state.currentSegmentData = null;
        dom.audioPlayer.play();
        startTimeSync();
        setAppState('singing');
        startHighlightLoop();
    };

    ws.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch (e) { return; }
        handleServerMessage(data);
    };

    ws.onclose = (event) => {
        console.warn("Game WebSocket fechado. Tentando reconectar...");
        if (game.cancelled()) return;
        if (state.currentAppState === 'idle' || state.currentAppState === 'game-over') return;
        if (event && event.code === DISPLAY_REPLACED_CODE) {
            // outra tela assumiu a sala: não briga por ela
            showToast('Outra tela assumiu esta sala.', 'error');
            resetGameState();
            return;
        }
        if (attempt >= MAX_RECONNECT_ATTEMPTS) {
            console.error("Número máximo de tentativas de reconexão atingido. Abortando jogo.");
            resetGameState();
            return;
        }
        attempt++;
        const delay = Math.min(1000 * attempt, 5000);
        console.log(`Tentativa de reconexão ${attempt}/${MAX_RECONNECT_ATTEMPTS} em ${delay}ms...`);
        state.gameReconnectTimer = setTimeout(() => connectGameWebSocket(game, attempt), delay);
    };

    ws.onerror = (err) => {
        console.error("Erro no WebSocket do jogo:", err);
    };
}

export async function startKaraoke() {
    const songId = state.selectedSongId;
    const generation = ++state.gameGeneration;
    keepScreenOn();  // TV/PC: sem descanso de tela durante a partida
    // "Voltar" durante um await cancela o início (resetGameState muda a geração)
    const cancelled = () => generation !== state.gameGeneration;

    await loadSegments(songId);
    if (cancelled()) return;

    // Escalação do lobby: um competidor por microfone (vagas repetidas = dupla/trio)
    if (!validateLobby()) {
        throw new Error('Nenhum cantor no lobby');
    }
    const lineup = lobbyLineup();

    // TV: nunca abre o microfone dela (só celulares cantam)
    const captureMic = !isTvBrowser && !!(state.localStreamForced || !state.isMobileMicrophoneConnected || lineup.mics.indexOf(PC_MIC) !== -1);
    await startGameAudio(captureMic);

    if (cancelled()) {
        await destroyAudio();
        return;
    }

    attachGuideSync();
    attachPlayerEvents();

    // Aplica o volume salvo ao GainNode do AudioLifecycleManager
    const savedVolume = localStorage.getItem('karaoke_backing_volume');
    if (savedVolume !== null && state.audioManager) {
        state.audioManager.setVolume(parseFloat(savedVolume));
    }

    closeRoomSocket();

    const scoringMode = currentScoringMode();
    state.activePlayers = lineup.mics;
    state.gameMode = lineup.mode;
    state.turnOrder = lineup.turns ? lineup.groups.map((g) => g.mics) : null;
    state.scoringMode = scoringMode;

    // Barras de placar nas bordas (a chamada tinha sumido no commit 8fc8799)
    setPlayersLayout(lineup);

    connectGameWebSocket({
        songId,
        lineup,
        scoringMode,
        sampleRate: state.audioContext.sampleRate,
        cancelled,
    }, 0);

    dom.audioPlayer.playbackRate = state.currentSpeed;
}
