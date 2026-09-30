import { state, setAppState } from './state.js';
import { iconSvg } from './icons.js';
import { lobbyLineup, validateLobby, setAvailableMics, micLabel, groupName, PC_MIC } from './lobby.js';
import { showScoreBars, hideScoreBars, updateScoreBars, groupFinalScores } from './score-bars.js';
import { stampVerse, clearStamp, verseQuality, replayClass } from './verse-stamp.js';
import { keepScreenOn, allowScreenOff } from './wake-lock.js';
import { attachGuideSync, savedGuideVolume } from './guide-vocal.js';
import { openShareCard } from './share-card.js';
import { toggleReplay, stopReplay } from './replay.js';
import { turnOwner } from './turns.js';
import { onRequestsUpdate, showNextUp, stopAutoNext } from './requests.js';
import { escapeHtml } from './html.js';
import { dom } from './dom.js';
import { myRoom, DISPLAY_REPLACED_CODE } from './config.js';
import { showToast } from './toast.js';
import { AudioLifecycleManager } from './audio-lifecycle-manager.js';
import { updateSyncDisplay, startTimeSync, stopTimeSync } from './sync.js';
import { updateMicStatusPanel } from './mic-status.js';
import { connectDisplayWebSocket } from './ws-display.js';
import { showAnnotationButton } from './annotate.js';
import { fillLine, fillWord, setLyricsScriptAvailable } from './lyrics-script.js';

// Linha que passa a conter spans de palavra: deixa de ser redesenhada como linha
// inteira quando o modo de escrita (original/romaji/ambos) muda.
function clearLine(el) {
    el.classList.remove('lyrics-line');
    delete el.dataset.original;
    delete el.dataset.romaji;
    el.innerHTML = '';
}

// Japonês em kanji/kana não separa palavras com espaço; letra em romaji e trechos
// em inglês separam (espelha separator_between em server/lyrics_text.py).
const JA_SCRIPT_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u3005]/; // kana + kanji + 々
function wordSeparator(language, word, nextWord) {
    const japanese = (language || '').toLowerCase().startsWith('ja');
    if (japanese && JA_SCRIPT_RE.test(word) && (!nextWord || JA_SCRIPT_RE.test(nextWord))) return '';
    return ' ';
}

export async function resetGameState() {
    const gameOverModal = document.getElementById('game-over-modal');
    if (gameOverModal) gameOverModal.removeAttribute('data-open');
    showAnnotationButton(null);

    if (state.slideTransitionCleanup) {
        state.slideTransitionCleanup();
    }
    if (state.transcriptionActiveTimer) {
        clearTimeout(state.transcriptionActiveTimer);
        state.transcriptionActiveTimer = null;
    }
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
    if (state.ws) {
        state.ws.onclose = null;
        state.ws.close();
        state.ws = null;
    }
    if (state.audioManager) {
        await state.audioManager.destroy();
        state.audioManager = null;
    }
    state.localStream = null;
    state.micProcessorNode = null;
    state.micSourceNode = null;
    state.audioContext = null;
    state.mediaElementSource = null;
    state.jungleNode = null;

    state.currentTranspose = 0;
    state.currentSpeed = 1.0;
    state.isUserDraggingProgress = false;
    if (dom.pitchValue) dom.pitchValue.innerText = 'Normal';
    if (dom.speedValue) dom.speedValue.innerText = '1.0x';
    if (dom.songProgressSlider) {
        dom.songProgressSlider.value = 0;
        dom.songProgressSlider.style.background = 'var(--track)';
    }
    if (state.animationId) {
        cancelAnimationFrame(state.animationId);
        state.animationId = null;
    }
    setAppState('idle');

    state.isSingingActive = false;
    state.isOutroActive = false;
    dom.audioPlayer.pause();
    dom.audioPlayer.src = '';

    document.getElementById('seg-score').innerText = '0%';
    const statsSyncVal = document.getElementById('stats-sync-value');
    if (statsSyncVal) statsSyncVal.innerText = '0ms';
    const timeCurrent = document.getElementById('song-time-current');
    if (timeCurrent) timeCurrent.innerText = '0:00';
    const timeRemaining = document.getElementById('song-time-remaining');
    if (timeRemaining) timeRemaining.innerText = '-0:00';

    const transText = document.getElementById('transcription-text');
    if (transText) {
        transText.innerHTML = '<strong>Ouvi:</strong> <span class="muted">[Aguardando canto...]</span>';
    }

    const scoreFill = document.getElementById('score-progress-fill');
    if (scoreFill) {
        scoreFill.style.height = '0%';
        scoreFill.style.width = '';
    }
    document.getElementById('score-percentage-text').innerText = '0%';
    const pitchAvg = document.getElementById('pitch-avg-text');
    if (pitchAvg) pitchAvg.hidden = true;

    const perfBorder = document.getElementById('perf-border-overlay');
    if (perfBorder) {
        perfBorder.className = 'perf-border-idle';
    }
    clearStamp(document.getElementById('verse-stamp'));
    const segScoreReset = document.getElementById('seg-score');
    if (segScoreReset) delete segScoreReset.dataset.quality;

    const verseContainer = document.getElementById('verse-progress-container');
    const verseFill = document.getElementById('verse-progress-fill');
    if (verseContainer && verseFill) {
        verseFill.style.width = '0%';
        verseContainer.removeAttribute('data-active');
    }

    const app = document.getElementById('app');
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

    document.getElementById('silence-progress-fill').style.width = '0%';

    const linePrev = document.getElementById('line-prev');
    if (linePrev) {
        linePrev.innerHTML = '';
        linePrev.className = 'carousel-line prev-line';
    }
    const lineCurr = document.getElementById('line-curr');
    if (lineCurr) {
        lineCurr.innerHTML = '';
        lineCurr.className = 'carousel-line curr-line';
    }
    const lineNext = document.getElementById('line-next');
    if (lineNext) {
        lineNext.innerHTML = '';
        lineNext.className = 'carousel-line next-line';
    }
    const lineUpcoming = document.getElementById('line-upcoming');
    if (lineUpcoming) {
        lineUpcoming.innerHTML = '';
        lineUpcoming.className = 'carousel-line upcoming-line';
    }
    const carouselInner = document.getElementById('carousel-inner');
    if (carouselInner) {
        carouselInner.classList.add('no-transition');
        carouselInner.style.transform = 'translateY(0)';
        carouselInner.offsetHeight;
        carouselInner.classList.remove('no-transition');
    }

    dom.btnStart.disabled = false;
    dom.btnStart.innerText = 'INICIAR';
    if (dom.btnPausePlay) {
        dom.btnPausePlay.innerText = 'PAUSAR';
        dom.btnPausePlay.removeAttribute('data-paused');
    }

    hideScoreBars();

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

export async function startKaraoke() {
    const capturedSongId = state.selectedSongId;
    const generation = ++state.gameGeneration;
    keepScreenOn();  // TV/PC: sem descanso de tela durante a partida
    // "Voltar" durante um await cancela o início (resetGameState muda a geração)
    const cancelled = () => generation !== state.gameGeneration;

    // Carrega o segments.json inteiro no front antes de iniciar
    try {
        const resp = await fetch(`/api/songs/${capturedSongId}`);
        if (!resp.ok) throw new Error("Falha ao carregar os segmentos da música");
        const songData = await resp.json();
        state.currentSegments = songData.segments;
        console.log(`Carregados ${state.currentSegments.length} segmentos para a música localmente.`);
    } catch (err) {
        console.error("Erro ao pré-carregar os segmentos:", err);
        // main.js mostra o erro e libera o botão INICIAR
        throw new Error("não foi possível carregar a música");
    }
    if (cancelled()) return;

    // Escalação do lobby: um competidor por microfone (vagas repetidas = dupla/trio)
    if (!validateLobby()) {
        throw new Error('Nenhum cantor no lobby');
    }
    const lineup = lobbyLineup();
    const mode = lineup.mode;
    const activeList = lineup.mics;

    const captureMic = !!(state.localStreamForced || !state.isMobileMicrophoneConnected || activeList.indexOf(PC_MIC) !== -1);

    if (state.audioManager) {
        await state.audioManager.destroy();
        state.audioManager = null;
    }

    state.audioManager = new AudioLifecycleManager({
        captureMic: captureMic,
        mediaElement: dom.audioPlayer,
        guideElement: dom.guidePlayer,
        guideVolume: savedGuideVolume(),
        onAudioChunk: (data) => {
            // Música inteira, não só os versos (ver mobile-mic-view.js). Fora do
            // jogo o servidor descarta: sem relógio da música não há onde encaixar.
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(data);
            }
        }
    });
    state.audioManager.currentTranspose = state.currentTranspose;

    try {
        await state.audioManager.init();
        await state.audioManager.start();

        state.audioContext = state.audioManager.audioContext;
        state.localStream = state.audioManager.localStream;
        state.micSourceNode = state.audioManager.micSourceNode;
        state.micProcessorNode = state.audioManager.micProcessorNode;
        state.mediaElementSource = state.audioManager.mediaElementSource;
        state.jungleNode = state.audioManager.jungleNode;
    } catch (err) {
        if (captureMic) {
            console.warn("Sem microfone local detectado. Continuando apenas para reprodução...", err);
            if (!state.isMobileMicrophoneConnected) {
                showToast("Modo som de fundo ativo (sem microfone local)", "warning");
            }
            if (state.audioManager) {
                await state.audioManager.destroy();
            }
            state.audioManager = new AudioLifecycleManager({
                captureMic: false,
                mediaElement: dom.audioPlayer,
                guideElement: dom.guidePlayer,
                guideVolume: savedGuideVolume(),
            });
            state.audioManager.currentTranspose = state.currentTranspose;
            await state.audioManager.init();
            await state.audioManager.start();

            state.audioContext = state.audioManager.audioContext;
            state.localStream = null;
            state.micSourceNode = null;
            state.micProcessorNode = null;
            state.mediaElementSource = state.audioManager.mediaElementSource;
            state.jungleNode = state.audioManager.jungleNode;
        } else {
            throw err;
        }
    }

    if (cancelled()) {
        if (state.audioManager) await state.audioManager.destroy();
        state.audioManager = null;
        return;
    }

    attachGuideSync();

    // Aplica o volume salvo ao GainNode do AudioLifecycleManager
    const savedVolume = localStorage.getItem('karaoke_backing_volume');
    if (savedVolume !== null && state.audioManager) {
        state.audioManager.setVolume(parseFloat(savedVolume));
    }

    const sampleRate = state.audioContext.sampleRate;

    if (state.ws) {
        try {
            state.ws.onclose = null;
            state.ws.close();
        } catch (e) { }
        state.ws = null;
    }

    const scoringMode = (dom.btnScoreMode && dom.btnScoreMode.getAttribute('data-mode')) || 'timing';

    state.activePlayers = activeList;
    state.gameMode = mode;
    state.turnOrder = lineup.turns ? lineup.groups.map((g) => g.mics) : null;
    state.scoringMode = scoringMode;

    // Barras de placar nas bordas (a chamada tinha sumido no commit 8fc8799).
    // data-players/-count: states.css esconde o placar solo e reserva espaço.
    const appEl = document.getElementById('app');
    if (activeList.length > 1) {
        showScoreBars(lineup.groups);
        appEl.setAttribute('data-players', 'multi');
        appEl.setAttribute('data-player-count', String(Math.min(4, lineup.groups.length)));
        if (lineup.mode === 'teams') appEl.setAttribute('data-teams', '');
        else appEl.removeAttribute('data-teams');
    } else {
        hideScoreBars();
    }

    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connectGameWebSocket() {
        state.gameReconnectTimer = null;
        if (cancelled()) return;
        // Reconexão no meio da música: o servidor mantém placar e gravação
        // (resume=1) e o front não reinicia a música nem a tela.
        const resuming = reconnectAttempts > 0;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/room/${encodeURIComponent(myRoom)}?role=display&song_id=${encodeURIComponent(capturedSongId)}${resuming ? '&resume=1' : ''}`;
        state.ws = new WebSocket(wsUrl);
        state.ws.binaryType = 'arraybuffer';

        state.ws.onopen = () => {
            reconnectAttempts = 0;

            state.ws.send(JSON.stringify({ type: "client_info", sample_rate: sampleRate }));
            if (resuming) {
                startTimeSync();
                return;
            }
            state.ws.send(JSON.stringify({
                type: "start_game",
                game_mode: mode,
                active_players: activeList,
                scoring_mode: scoringMode,
                transpose: state.currentTranspose || 0,
                turns: !!state.turnOrder,
                turn_order: state.turnOrder || undefined
            }));

            state.isFirstSegment = true;
            state.currentSegmentData = null;
            dom.audioPlayer.play();
            startTimeSync();
            setAppState('singing');
            startHighlightLoop();
        };

        state.ws.onmessage = (event) => {
            let data;
            try { data = JSON.parse(event.data); } catch (e) { return; }
            handleServerMessage(data);
        };

        state.ws.onclose = (event) => {
            console.warn("Game WebSocket fechado. Tentando reconectar...");
            if (cancelled()) return;
            if (state.currentAppState === 'idle' || state.currentAppState === 'game-over') return;
            if (event && event.code === DISPLAY_REPLACED_CODE) {
                // outra tela assumiu a sala: não briga por ela
                showToast('Outra tela assumiu esta sala.', 'error');
                resetGameState();
                return;
            }
            if (reconnectAttempts >= maxReconnectAttempts) {
                console.error("Número máximo de tentativas de reconexão atingido. Abortando jogo.");
                resetGameState();
                return;
            }
            reconnectAttempts++;
            const delay = Math.min(1000 * reconnectAttempts, 5000);
            console.log(`Tentativa de reconexão ${reconnectAttempts}/${maxReconnectAttempts} em ${delay}ms...`);
            state.gameReconnectTimer = setTimeout(connectGameWebSocket, delay);
        };

        state.ws.onerror = (err) => {
            console.error("Erro no WebSocket do jogo:", err);
        };
    }

    connectGameWebSocket();

    dom.audioPlayer.playbackRate = state.currentSpeed;
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
    players_update(data, context) {
        const { dom } = context;
        if (dom.mpConnectedCount) dom.mpConnectedCount.innerText = data.players.length;
        if (dom.mpQueueCount) dom.mpQueueCount.innerText = data.queue_count;

        // Microfones disponíveis para as vagas do lobby
        setAvailableMics(data.players);
    },
    pairing_status(data, context) {
        const { state } = context;
        const pairingStatusText = document.getElementById('pairing-status-text');
        const pairingStatusDot = document.getElementById('pairing-status-dot');

        if (data.status === 'paired') {
            state.isMobileMicrophoneConnected = true;
            updateMicStatusPanel();
            if (pairingStatusText) {
                pairingStatusText.innerText = 'Celular conectado com sucesso!';
            }
            const statusBox = document.getElementById('pairing-status-box');
            if (statusBox) {
                statusBox.setAttribute('data-status', 'paired');
            }
            showToast("Microfone sem fio pareado e ativo!", "success");
        } else if (data.status === 'unpaired') {
            state.isMobileMicrophoneConnected = false;
            updateMicStatusPanel();
            if (pairingStatusText) {
                pairingStatusText.innerText = "Aguardando conexão do celular...";
            }
            const statusBox = document.getElementById('pairing-status-box');
            if (statusBox) {
                statusBox.removeAttribute('data-status');
            }
            showToast("Microfone sem fio desconectado.", "error");
        }
    },
    singing_state(data, context) {
        const { state } = context;
        if (state.currentSegments) return;
        state.isSingingActive = data.active;
        const transText = document.getElementById('transcription-text');
        if (transText && !state.transcriptionActiveTimer) {
            transText.innerHTML = `<strong>Ouvi:</strong> <span class="muted">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
        }
    },
    outro_start(data, context) {
        const { state, dom } = context;
        state.isOutroActive = true;
        state.outroStartPlayerTime = dom.audioPlayer.currentTime;
        state.outroTotalDuration = Math.max(1, dom.audioPlayer.duration - state.outroStartPlayerTime);

        setAppState('scoring');

        const transText = document.getElementById('transcription-text');
        if (transText) {
            transText.innerHTML = '<strong>Ouvi:</strong> <span class="muted">[Show finalizado!]</span>';
        }
    },
    segment_start(data, context) {
        const { state } = context;
        if (state.currentSegments) return;
        if (!state.transcriptionActiveTimer) {
            const transText = document.getElementById('transcription-text');
            if (transText) {
                transText.innerHTML = '<strong>Ouvi:</strong> <span class="muted">[Solo Instrumental...]</span>';
            }
        }
        renderLyrics(data);
        startHighlightLoop();
    },
    segment_result(data, context) {
        const { state } = context;
        // Recálculo após voltar a música: só atualiza os totais, sem nota de verso
        if (data.recalc) {
            applyTotals(data);
            return;
        }
        const segScore = document.getElementById('seg-score');
        segScore.innerText = data.score + '%';
        segScore.dataset.quality = verseQuality(data.score).key;
        replayClass(segScore, 'seg-score--pulse');
        // carimbo no palco só no solo; em disputa cada barra tem o seu
        if (!(state.activePlayers && state.activePlayers.length > 1)) {
            stampVerse(document.getElementById('verse-stamp'), data.score, 0, data.pitch);
        }
        const transText = document.getElementById('transcription-text');

        if (data.transcription && data.transcription.trim()) {
            const words = data.transcription.split(/\s+/);
            transText.innerHTML = '<strong>Ouvi:</strong> ';

            const expectedNormalized = state.lastSegmentLyricsTimed
                ? state.lastSegmentLyricsTimed.map(w => normalizeWord(w.word))
                : [];

            words.forEach(word => {
                const cleanWord = normalizeWord(word);
                const isMatch = expectedNormalized.includes(cleanWord);

                const span = document.createElement('span');
                span.innerText = word + ' ';
                span.className = isMatch ? 'heard-word heard-word--hit' : 'heard-word heard-word--miss';
                transText.appendChild(span);
            });

            if (state.transcriptionActiveTimer) clearTimeout(state.transcriptionActiveTimer);
            state.transcriptionActiveTimer = setTimeout(() => {
                state.transcriptionActiveTimer = null;
                if (state.currentAppState !== 'idle') {
                    transText.innerHTML = `<strong>Ouvi:</strong> <span class="muted">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                }
            }, 3500);
        } else {
            transText.innerHTML = '<strong>Ouvi:</strong> <span class="muted">[Silêncio ou Incompreensível]</span>';
            if (state.transcriptionActiveTimer) clearTimeout(state.transcriptionActiveTimer);
            state.transcriptionActiveTimer = setTimeout(() => {
                state.transcriptionActiveTimer = null;
                if (state.currentAppState !== 'idle') {
                    transText.innerHTML = `<strong>Ouvi:</strong> <span class="muted">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                }
            }, 3500);
        }

        applyTotals(data);

        // Update performance border overlay based on the last segment score
        const lastSegmentScore = parseFloat(data.score) || 0;
        // em disputa a nota geral mistura os times: a moldura fica só no solo
        const isMulti = state.activePlayers && state.activePlayers.length > 1;
        const perfBorder = isMulti ? null : document.getElementById('perf-border-overlay');
        if (perfBorder) {
            perfBorder.className = ''; // Reset classes
            perfBorder.className = `perf-border-${verseQuality(lastSegmentScore).key}`;

            if (state.perfBorderTimer) {
                clearTimeout(state.perfBorderTimer);
            }
            state.perfBorderTimer = setTimeout(() => {
                perfBorder.className = 'perf-border-idle';
                state.perfBorderTimer = null;
            }, 2000);
        }

        // Atualização de scores no modo Multiplayer
        if (data.player_scores && state.activePlayers && state.activePlayers.length > 1) {
            const expectedNormalized = state.lastSegmentLyricsTimed
                ? state.lastSegmentLyricsTimed.map(w => normalizeWord(w.word))
                : [];
            // Barra por time + barrinha de cada membro (score-bars.js)
            updateScoreBars(data.player_scores, expectedNormalized, renderTranscriptionInto);
        }
    },
    game_over(data, context) {
        const { dom } = context;
        dom.audioPlayer.pause();
        setAppState('game-over');
        state.lastGameOver = data;
        showGameOverModal(parseFloat(data.total_score) || 0, data.player_scores);
        showGameOverExtras(data);
        showNextUp();
        showAnnotationButton(data.recording_id);
    }
};

// Nota geral (lateral). No recálculo (voltou a música) também atualiza as
// barras do multiplayer, só os números.
function applyTotals(data) {
    const pitchEl = document.getElementById('pitch-avg-text');
    if (pitchEl && typeof data.pitch_avg === 'number') {
        pitchEl.textContent = `Tom ${Math.round(data.pitch_avg)}%`;
        pitchEl.hidden = false;
    }
    const val = parseFloat(data.total_score) || 0;
    const scoreFill = document.getElementById('score-progress-fill');
    if (scoreFill) scoreFill.style.height = val + '%';
    document.getElementById('score-percentage-text').innerText = val.toFixed(1) + '%';
    if (data.recalc && data.player_scores && state.activePlayers && state.activePlayers.length > 1) {
        updateScoreBars(data.player_scores, [], renderTranscriptionInto, { recalc: true });
    }
}

// Revezar versos: selo "Vez de ..." no palco e destaque da barra do time da vez
function showTurn(owner) {
    const badge = document.getElementById('turn-badge');
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
        const bar = document.getElementById(`mp-score-bar-p${i + 1}`);
        if (!bar) return;
        bar.classList.toggle('mp-score-bar--turn', i === gi);
        bar.classList.toggle('mp-score-bar--waiting', i !== gi);
    });
}

const COUNTDOWN_SEC = 3;

// Contagem antes de voltar a cantar (n = 3, 2, 1; null esconde).
function setCountdown(n) {
    const el = document.getElementById('verse-countdown');
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
    players.slice(0, 4).forEach((player) => {
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
function showGameOverExtras(data) {
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
export function shareDataFromGameOver(data) {
    const title = document.getElementById('current-song-title');
    const artist = document.getElementById('current-song-artist');
    const scores = data.player_scores || {};
    const names = Object.keys(scores);
    const key = soloKey(data);
    const teams = groupFinalScores(scores);
    let podium = null;
    if (teams && teams.length > 1) {
        podium = teams.map((t) => ({
            name: t.members.length > 1 ? `${groupName(t.members.length)} ${t.group.team}` : micLabel(t.members[0].mic),
            score: t.score,
        }));
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

export function handleServerMessage(data) {
    const handler = DISPLAY_HANDLERS[data.type];
    if (handler) {
        const context = { state, dom, myRoom };
        handler(data, context);
    } else {
        console.warn(`Tipo de mensagem de display desconhecido recebido: ${data.type}`);
    }
}

export function showGameOverModal(finalScore, playerScores) {
    const modal = document.getElementById('game-over-modal');
    const rankBadge = document.getElementById('rank-badge');
    const rankTitle = document.getElementById('rank-title');
    const modalScore = document.getElementById('modal-score');

    modalScore.innerText = finalScore.toFixed(1) + '%';

    let rank = 'C';
    let title = 'PRECISA PRATICAR!';

    if (finalScore >= 95) {
        rank = 'S'; title = 'PERFORMANCE LENDÁRIA!';
    } else if (finalScore >= 85) {
        rank = 'A'; title = 'EXCELENTE APRESENTAÇÃO!';
    } else if (finalScore >= 70) {
        rank = 'B'; title = 'BOM TRABALHO!';
    }

    // cor do rank vem do CSS (.rank-badge[data-rank])
    rankBadge.innerText = rank;
    rankBadge.dataset.rank = rank;
    const rankSeal = rankBadge.parentNode;
    rankTitle.innerText = title;

    // Times (duplas/trios): o pódio mostra a nota do time, média dos membros
    const teamResults = playerScores ? groupFinalScores(playerScores) : null;
    const teamMembers = {};
    if (teamResults) {
        playerScores = {};
        teamResults.forEach((r) => {
            const name = r.members.length > 1 ? `${groupName(r.members.length)} ${r.group.team}` : micLabel(r.members[0].mic);
            playerScores[name] = r.score;
            if (r.members.length > 1) {
                teamMembers[name] = r.members.map((m) => `${micLabel(m.mic)} ${Math.round(m.score)}%`).join(' · ');
            }
        });
    }
    const membersHtml = (name) => (teamMembers[name] ? `<span class="podium-members">${escapeHtml(teamMembers[name])}</span>` : '');
    const sortedPlayers = playerScores ? Object.entries(playerScores).sort((a, b) => b[1] - a[1]) : [];
    const numPlayers = sortedPlayers.length;

    // Remove any old podium if present
    const oldPodium = document.getElementById('podium-area');
    if (oldPodium) {
        oldPodium.remove();
    }

    if (numPlayers > 1) {
        // Multiplayer: Show podium & hide solo rank components
        rankSeal.hidden = true;
        rankTitle.hidden = true;

        const podiumArea = document.createElement('div');
        podiumArea.id = 'podium-area';
        podiumArea.className = 'podium-container';
        
        // Insert podium before the average score box
        const scoreBox = modalScore.parentNode;
        scoreBox.parentNode.insertBefore(podiumArea, scoreBox);

        const first = sortedPlayers[0];
        const second = sortedPlayers[1];
        const third = sortedPlayers[2];
        const fourth = sortedPlayers[3];

        const formatName = (name) => escapeHtml(micLabel(name));

        let columnsHtml = '';

        // 2nd Place
        if (second) {
            columnsHtml += `
                <div class="podium-col podium-2nd">
                    <span class="podium-name" title="${formatName(second[0])}">${formatName(second[0])}</span>
                    ${membersHtml(second[0])}
                    <span class="podium-score">${second[1].toFixed(1)}%</span>
                    <div class="podium-pedestal">2</div>
                </div>
            `;
        }

        // 1st Place
        if (first) {
            columnsHtml += `
                <div class="podium-col podium-1st">
                    <span class="podium-crown">${iconSvg('crown')}</span>
                    <span class="podium-name" title="${formatName(first[0])}">${formatName(first[0])}</span>
                    ${membersHtml(first[0])}
                    <span class="podium-score">${first[1].toFixed(1)}%</span>
                    <div class="podium-pedestal">1</div>
                </div>
            `;
        }

        // 3rd Place
        if (third) {
            columnsHtml += `
                <div class="podium-col podium-3rd">
                    <span class="podium-name" title="${formatName(third[0])}">${formatName(third[0])}</span>
                    ${membersHtml(third[0])}
                    <span class="podium-score">${third[1].toFixed(1)}%</span>
                    <div class="podium-pedestal">3</div>
                </div>
            `;
        } else if (second) {
            // Spacer to keep 1st place centered when only 2 players are on the podium
            columnsHtml += `<div class="podium-col podium-col--spacer"></div>`;
        }

        podiumArea.innerHTML = `
            <div class="podium-columns">
                ${columnsHtml}
            </div>
            <div id="podium-extra-list" class="podium-extra-list"></div>
        `;

        const extraList = document.getElementById('podium-extra-list');
        if (fourth && extraList) {
            const item = document.createElement('div');
            item.className = 'podium-extra-item';
            item.innerHTML = `<span>4º Lugar: ${formatName(fourth[0])}</span><span class="score-num">${fourth[1].toFixed(1)}%</span>`;
            extraList.appendChild(item);
        }
    } else {
        // Solo: Show solo rank components & hide podium
        rankSeal.hidden = false;
        rankTitle.hidden = false;
    }

    // Placar multiplayer no modal (only shown in solo or fallback)
    let breakdownDiv = document.getElementById('modal-mp-breakdown');
    if (!breakdownDiv) {
        breakdownDiv = document.createElement('div');
        breakdownDiv.id = 'modal-mp-breakdown';
        breakdownDiv.className = 'mp-breakdown';
        modalScore.parentNode.appendChild(breakdownDiv);
    }

    breakdownDiv.innerHTML = '';
    if (playerScores && Object.keys(playerScores).length > 0 && numPlayers <= 1) {
        breakdownDiv.hidden = false;
        sortedPlayers.forEach(([name, score], idx) => {
            const item = document.createElement('div');
            item.className = 'mp-breakdown__row';
            const medal = `<span class="place-num">${idx + 1}º</span>`;
            const displayName = escapeHtml(micLabel(name));
            item.innerHTML = `<span>${medal} ${displayName}</span><span>${score.toFixed(1)}%</span>`;
            breakdownDiv.appendChild(item);
        });
    } else {
        breakdownDiv.hidden = true;
    }

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

// Compara palavras sem acento e pontuação ("não" == "nao"). O \w do JS só
// cobre ASCII: com ele "não" virava "no" e o acerto aparecia como erro.
export function normalizeWord(word) {
    return String(word).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
}

export function renderTranscriptionInto(container, transcription, expectedNormalized, showHeader = true) {
    if (!container) return;
    container.innerHTML = '';
    
    if (!transcription || !transcription.trim()) {
        container.innerHTML = showHeader ? '<strong>Ouvi:</strong> <span class="muted">[Silêncio]</span>' : '<span class="muted">[Silêncio]</span>';
        return;
    }

    if (showHeader) {
        container.innerHTML = '<strong>Ouvi:</strong> ';
    }
    const words = transcription.split(/\s+/);
    words.forEach(word => {
        const cleanWord = normalizeWord(word);
        const isMatch = expectedNormalized.includes(cleanWord);

        const span = document.createElement('span');
        span.innerText = word + ' ';
        span.className = isMatch ? 'heard-word heard-word--hit' : 'heard-word heard-word--miss';
        container.appendChild(span);
    });
}

function getTranslationForLine(line) {
    const container = document.querySelector('.carousel-container');
    const inner = document.getElementById('carousel-inner');
    if (!container || !inner || !line) return 0;
    
    // Get the line's center relative to the top of carousel-inner
    const lineCenter = line.offsetTop + line.offsetHeight / 2;
    
    // The container's center relative to its padding box is container.clientHeight / 2.
    // So the translation to align the line center with the container center is:
    return (container.clientHeight / 2) - lineCenter;
}

// Window resize handler to maintain active line centering
window.addEventListener('resize', () => {
    if (state.isSingingActive || (state.currentSegmentData && state.currentAppState !== 'idle')) {
        const carouselInner = document.getElementById('carousel-inner');
        if (carouselInner) {
            carouselInner.classList.add('no-transition');
            const targetLine = state.slideTransitionCleanup ? dom.nextLyricsDisplay : dom.lyricsDisplay;
            if (targetLine) {
                const translation = getTranslationForLine(targetLine);
                carouselInner.style.transform = `translateY(${translation}px)`;
            }
            carouselInner.offsetHeight; // force reflow
            carouselInner.classList.remove('no-transition');
        }
    }
});

export function renderLyrics(data) {
    setLyricsScriptAvailable(data.lyrics_romaji);
    const virtualTime = dom.audioPlayer.currentTime + state.syncOffset;
    const pauseTime = data.sing_start - virtualTime;

    if (pauseTime > 3.0) {
        state.totalPauseDuration = pauseTime;
        state.pauseStartTarget = data.sing_start;
    } else {
        state.totalPauseDuration = 0;
        state.pauseStartTarget = 0;
    }

    if (state.isFirstSegment) {
        state.isFirstSegment = false;
        state.lastSegmentLyricsTimed = null;
        state.currentSegmentData = data;
        updateLyricsDOM(data);
        
        // Initial center alignment
        const carouselInner = document.getElementById('carousel-inner');
        if (carouselInner) {
            carouselInner.classList.add('no-transition');
            const translation = getTranslationForLine(dom.lyricsDisplay);
            carouselInner.style.transform = `translateY(${translation}px)`;
            carouselInner.offsetHeight; // force reflow
            carouselInner.classList.remove('no-transition');
        }
        return;
    }

    // Resolve any previous pending transition immediately to avoid overlaps
    if (state.slideTransitionCleanup) {
        state.slideTransitionCleanup();
    }

    // Update state variables immediately so startHighlightLoop is in sync with the new segment's timing
    const oldSegmentData = state.currentSegmentData;
    state.lastSegmentLyricsTimed = oldSegmentData ? oldSegmentData.lyrics_timed : null;
    state.currentSegmentData = data;

    const linePrev = dom.prevLyricsDisplay;
    const lineCurr = dom.lyricsDisplay;
    const lineNext = dom.nextLyricsDisplay;
    const lineUpcoming = dom.upcomingLyricsDisplay;
    const carouselInner = document.getElementById('carousel-inner');

    if (!carouselInner) {
        // Fallback in case element is missing
        updateLyricsDOM(data);
        return;
    }

    // Strip IDs from current active words in line-curr to avoid duplicates in document.getElementById
    const currentSpans = lineCurr.querySelectorAll('.word');
    currentSpans.forEach(span => span.removeAttribute('id'));

    // Populate line-next with new lyrics
    if (state.syncMode === 'verse') {
        fillLine(lineNext, data.lyrics, data.lyrics_romaji);
    } else {
        clearLine(lineNext);
        data.lyrics_timed.forEach((item, idx) => {
            const span = document.createElement('span');
            span.className = 'word';
            fillWord(span, item.word, item.romaji, wordSeparator(data.language, item.word, (data.lyrics_timed[idx + 1] || {}).word));
            span.id = `word-${idx}`;
            lineNext.appendChild(span);
        });
    }

    // Set line-upcoming to show the incoming line next lyrics
    if (lineUpcoming) {
        fillLine(lineUpcoming, data.next_lyrics, data.next_lyrics_romaji);
    }

    // Calculate translation dynamically to center lineNext
    const translation = getTranslationForLine(lineNext);

    // Start transition
    carouselInner.style.transform = `translateY(${translation}px)`;
    linePrev.classList.add('line-prev-slide-out');
    lineCurr.classList.add('line-curr-to-prev');
    lineNext.classList.add('line-next-to-curr');
    if (lineUpcoming) {
        lineUpcoming.classList.add('line-upcoming-to-next');
    }

    // Define cleanup function to commit DOM values
    const commitTransition = () => {
        carouselInner.classList.add('no-transition');

        // Swap contents
        fillLine(linePrev, data.prev_lyrics, data.prev_lyrics_romaji);
        if (state.syncMode === 'verse') {
            fillLine(lineCurr, lineNext.dataset.original, lineNext.dataset.romaji);
        } else {
            clearLine(lineCurr);
            lineCurr.innerHTML = lineNext.innerHTML;
        }
        fillLine(lineNext, data.next_lyrics, data.next_lyrics_romaji);
        if (lineUpcoming) {
            fillLine(lineUpcoming, data.upcoming_lyrics, data.upcoming_lyrics_romaji);
        }

        // Reset transform to center the new current line (lineCurr) and remove transition classes
        const steadyTranslation = getTranslationForLine(lineCurr);
        carouselInner.style.transform = `translateY(${steadyTranslation}px)`;
        
        linePrev.classList.remove('line-prev-slide-out');
        lineCurr.classList.remove('line-curr-to-prev');
        lineNext.classList.remove('line-next-to-curr');
        if (lineUpcoming) {
            lineUpcoming.classList.remove('line-upcoming-to-next');
        }

        carouselInner.offsetHeight; // force reflow
        carouselInner.classList.remove('no-transition');

        state.slideTransitionCleanup = null;
    };

    const timeoutId = setTimeout(commitTransition, 400);

    state.slideTransitionCleanup = () => {
        clearTimeout(timeoutId);
        commitTransition();
    };
}

export function updateLyricsDOM(data) {
    setLyricsScriptAvailable(data.lyrics_romaji);
    fillLine(dom.prevLyricsDisplay, data.prev_lyrics, data.prev_lyrics_romaji);
    fillLine(dom.nextLyricsDisplay, data.next_lyrics, data.next_lyrics_romaji);
    if (dom.upcomingLyricsDisplay) {
        fillLine(dom.upcomingLyricsDisplay, data.upcoming_lyrics, data.upcoming_lyrics_romaji);
    }

    if (state.syncMode === 'verse') {
        fillLine(dom.lyricsDisplay, data.lyrics, data.lyrics_romaji);
    } else {
        clearLine(dom.lyricsDisplay);
        data.lyrics_timed.forEach((item, idx) => {
            const span = document.createElement('span');
            span.className = 'word';
            fillWord(span, item.word, item.romaji, wordSeparator(data.language, item.word, (data.lyrics_timed[idx + 1] || {}).word));
            span.id = `word-${idx}`;
            dom.lyricsDisplay.appendChild(span);
        });
    }
}

export function startHighlightLoop() {
    if (state.animationId) cancelAnimationFrame(state.animationId);

    function update() {
        try {
            const audioPlayer = dom.audioPlayer;
            if (audioPlayer.duration && !state.isUserDraggingProgress) {
                const cur = audioPlayer.currentTime;
                const dur = audioPlayer.duration;
                const pct = Math.max(0, Math.min(100, (cur / dur) * 100));

                const formatTime = (secs) => {
                    const m = Math.floor(secs / 60);
                    const s = Math.floor(secs % 60);
                    return `${m}:${s < 10 ? '0' : ''}${s}`;
                };

                if (dom.songProgressSlider) {
                    dom.songProgressSlider.value = pct;
                    dom.songProgressSlider.style.background = `linear-gradient(to right, var(--accent) ${pct}%, var(--track) ${pct}%)`;
                }
                const timeCurrent = document.getElementById('song-time-current');
                if (timeCurrent) timeCurrent.innerText = formatTime(cur);
                const timeRemaining = document.getElementById('song-time-remaining');
                if (timeRemaining) timeRemaining.innerText = '-' + formatTime(Math.max(0, dur - cur));
            }

            if (state.isOutroActive && audioPlayer.duration) {
                const cur = audioPlayer.currentTime;
                const elapsed = cur - state.outroStartPlayerTime;
                const remaining = Math.max(0, audioPlayer.duration - cur);

                const pct = Math.max(0, Math.min(100, (elapsed / state.outroTotalDuration) * 100));

                const outroFill = document.getElementById('outro-progress-fill');
                if (outroFill) outroFill.style.width = pct + '%';

                const outroText = document.getElementById('outro-timer-text');
                if (outroText) outroText.innerText = `Finalizando em ${remaining.toFixed(1)}s...`;

                return;
            }

            const virtualTime = audioPlayer.currentTime + state.syncOffset;

            // Sincronia e transição local de segmentos
            if (state.currentSegments) {
                let new_idx = state.currentSegments.length;
                for (let idx = 0; idx < state.currentSegments.length; idx++) {
                    const seg = state.currentSegments[idx];
                    if (virtualTime < seg.sing_end) {
                        new_idx = idx;
                        break;
                    }
                }

                if (new_idx < state.currentSegments.length) {
                    const currentSeg = state.currentSegments[new_idx];

                    if (!state.currentSegmentData || state.currentSegmentData.id !== currentSeg.id) {
                        const prev_lyrics = new_idx > 0 ? state.currentSegments[new_idx - 1].lyrics : "";
                        const next_lyrics = new_idx < state.currentSegments.length - 1 ? state.currentSegments[new_idx + 1].lyrics : "";
                        const upcoming_lyrics = new_idx < state.currentSegments.length - 2 ? state.currentSegments[new_idx + 2].lyrics : "";
                        // Japonês: romaji das linhas vizinhas (undefined nos outros idiomas)
                        const romajiAt = (i) => state.currentSegments[i] && state.currentSegments[i].lyrics_romaji;

                        const segmentData = {
                            ...currentSeg,
                            prev_lyrics,
                            next_lyrics,
                            upcoming_lyrics,
                            prev_lyrics_romaji: romajiAt(new_idx - 1),
                            next_lyrics_romaji: romajiAt(new_idx + 1),
                            upcoming_lyrics_romaji: romajiAt(new_idx + 2),
                        };

                        renderLyrics(segmentData);
                        showTurn(turnOwner(state.currentSegments, state.turnOrder, new_idx));
                    }

                    // Determinação do estado de canto de forma local
                    const SINGING_PRE_BUFFER_SEC = 1.0;
                    const POST_SING_BUFFER_SEC = 0.5;
                    const isSinging = (
                        (currentSeg.sing_start - SINGING_PRE_BUFFER_SEC)
                        <= virtualTime
                        && virtualTime <= (currentSeg.sing_end + POST_SING_BUFFER_SEC)
                    );

                    if (isSinging !== state.isSingingActive) {
                        state.isSingingActive = isSinging;
                        const transText = document.getElementById('transcription-text');
                        if (transText && !state.transcriptionActiveTimer) {
                            transText.innerHTML = `<strong>Ouvi:</strong> <span class="muted">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                        }
                    }
                } else {
                    if (state.currentSegments.length > 0 && !state.isOutroActive) {
                        const lastSeg = state.currentSegments[state.currentSegments.length - 1];
                        if (virtualTime >= lastSeg.sing_end) {
                            if (state.isSingingActive) {
                                state.isSingingActive = false;
                                const transText = document.getElementById('transcription-text');
                                if (transText && !state.transcriptionActiveTimer) {
                                    transText.innerHTML = `<strong>Ouvi:</strong> <span class="muted">[Solo Instrumental...]</span>`;
                                }
                            }
                        }
                    }
                }
            }

            if (!state.currentSegmentData) {
                return;
            }

            const segData = state.currentSegmentData;
            if (!segData || typeof segData.sing_start !== 'number') return;

            const relativeTime = virtualTime - segData.sing_start;

            if (state.totalPauseDuration > 3.0) {
                const remainingTime = state.pauseStartTarget - virtualTime;
                const app = document.getElementById('app');

                if (remainingTime > COUNTDOWN_SEC) {
                    if (app) app.setAttribute('data-silence', 'true');
                    setCountdown(null);
                    const fill = document.getElementById('silence-progress-fill');
                    const text = document.getElementById('silence-timer-text');
                    const pct = Math.max(0, Math.min(100, ((remainingTime - COUNTDOWN_SEC) / (state.totalPauseDuration - COUNTDOWN_SEC)) * 100));
                    if (fill) fill.style.width = pct + '%';
                    if (text) text.innerText = remainingTime.toFixed(1) + 's';
                } else if (remainingTime > 0.1) {
                    // 3… 2… 1 por cima da próxima linha: depois de um solo muita gente entrava atrasada
                    if (app) app.removeAttribute('data-silence');
                    setCountdown(Math.ceil(remainingTime));
                } else {
                    if (app) app.removeAttribute('data-silence');
                    setCountdown(null);
                    state.totalPauseDuration = 0;
                    state.pauseStartTarget = 0;
                }
            } else {
                const app = document.getElementById('app');
                if (app) app.removeAttribute('data-silence');
                setCountdown(null);
            }

            const verseContainer = document.getElementById('verse-progress-container');
            const verseFill = document.getElementById('verse-progress-fill');
            if (verseContainer && verseFill) {
                const segStart = segData.sing_start;
                const segEnd = segData.sing_end;
                const duration = segEnd - segStart;

                if (virtualTime >= segStart && virtualTime <= segEnd && duration > 0) {
                    const pct = Math.max(0, Math.min(100, ((virtualTime - segStart) / duration) * 100));
                    verseFill.style.width = pct + '%';
                    verseContainer.setAttribute('data-active', 'true');
                } else if (virtualTime > segEnd) {
                    verseFill.style.width = '100%';
                    verseContainer.setAttribute('data-active', 'ended');
                } else {
                    verseFill.style.width = '0%';
                    verseContainer.removeAttribute('data-active');
                }
            }

            if (state.syncMode === 'verse') {
                const lineCurr = document.getElementById('line-curr');
                if (lineCurr) {
                    if (relativeTime >= 0 && virtualTime <= segData.sing_end) {
                        lineCurr.classList.add('verse-active');
                    } else {
                        lineCurr.classList.remove('verse-active');
                    }
                }
            } else if (segData.lyrics_timed) {
                segData.lyrics_timed.forEach((item, idx) => {
                    const el = document.getElementById(`word-${idx}`);
                    if (!el) return;

                    if (relativeTime >= item.expected_start) {
                        el.classList.add('passed');
                        el.classList.remove('active');
                    } else {
                        el.classList.remove('passed');
                    }

                    const nextItem = segData.lyrics_timed[idx + 1];
                    if (relativeTime >= item.expected_start && (!nextItem || relativeTime < nextItem.expected_start)) {
                        el.classList.add('active');
                        el.classList.remove('passed');
                    } else {
                        if (relativeTime < item.expected_start) el.classList.remove('active');
                    }
                });
            }
        } catch (err) {
            console.error("Erro no loop de animação da letra:", err);
        } finally {
            if (state.currentAppState !== 'idle' && state.currentAppState !== 'game-over') {
                state.animationId = requestAnimationFrame(update);
            }
        }
    }
    update();
}

export function updateAudioGraph(transpose) {
    if (state.audioManager) {
        state.audioManager.updateTranspose(transpose);
        state.jungleNode = state.audioManager.jungleNode;
    }
    // a afinação compara com a melodia no tom que está tocando
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'transpose', semitones: transpose }));
    }
}

export function initGameControls() {
    // Estilo de pontuação: botão toggle único (tempo+palavras vs. só palavras),
    // no mesmo padrão do botão de sincronia de letras.
    if (dom.btnScoreMode) {
        const savedScoringMode = localStorage.getItem('karaoke_scoring_mode') || 'timing';
        setScoreMode(savedScoringMode);
        dom.btnScoreMode.onclick = () => {
            const current = dom.btnScoreMode.getAttribute('data-mode');
            setScoreMode(current === 'words' ? 'timing' : 'words');
        };
    }

    if (dom.btnPitchMinus) {
        dom.btnPitchMinus.onclick = () => {
            if (state.currentTranspose > -6) {
                state.currentTranspose--;
                updatePitchUI();
                updateAudioGraph(state.currentTranspose);
            }
        };
    }

    if (dom.btnPitchPlus) {
        dom.btnPitchPlus.onclick = () => {
            if (state.currentTranspose < 6) {
                state.currentTranspose++;
                updatePitchUI();
                updateAudioGraph(state.currentTranspose);
            }
        };
    }

    if (dom.btnSpeedMinus) {
        dom.btnSpeedMinus.onclick = () => {
            if (state.currentSpeed > 0.75) {
                state.currentSpeed = Math.round((state.currentSpeed - 0.05) * 100) / 100;
                updateSpeedUI();
                dom.audioPlayer.playbackRate = state.currentSpeed;
            }
        };
    }

    if (dom.btnSpeedPlus) {
        dom.btnSpeedPlus.onclick = () => {
            if (state.currentSpeed < 1.5) {
                state.currentSpeed = Math.round((state.currentSpeed + 0.05) * 100) / 100;
                updateSpeedUI();
                dom.audioPlayer.playbackRate = state.currentSpeed;
            }
        };
    }

    if (dom.btnPausePlay) {
        dom.btnPausePlay.onclick = () => {
            if (dom.audioPlayer.paused) {
                dom.audioPlayer.play();
                dom.btnPausePlay.innerText = 'PAUSAR';
                dom.btnPausePlay.removeAttribute('data-paused');
                if (state.audioContext && state.audioContext.state === 'suspended') {
                    state.audioContext.resume();
                }
            } else {
                dom.audioPlayer.pause();
                dom.btnPausePlay.innerText = 'RETOMAR';
                dom.btnPausePlay.setAttribute('data-paused', 'true');
            }
        };
    }

    if (dom.songProgressSlider) {
        dom.songProgressSlider.oninput = (e) => {
            state.isUserDraggingProgress = true;
            const pct = parseFloat(e.target.value);
            dom.songProgressSlider.style.background = `linear-gradient(to right, var(--accent) ${pct}%, var(--track) ${pct}%)`;

            if (dom.audioPlayer.duration) {
                const targetTime = (pct / 100) * dom.audioPlayer.duration;
                const formatTime = (secs) => {
                    const m = Math.floor(secs / 60);
                    const s = Math.floor(secs % 60);
                    return `${m}:${s < 10 ? '0' : ''}${s}`;
                };

                const timeCurrent = document.getElementById('song-time-current');
                if (timeCurrent) timeCurrent.innerText = formatTime(targetTime);
                const timeRemaining = document.getElementById('song-time-remaining');
                if (timeRemaining) timeRemaining.innerText = '-' + formatTime(Math.max(0, dom.audioPlayer.duration - targetTime));
            }
        };

        dom.songProgressSlider.onchange = (e) => {
            state.isUserDraggingProgress = false;
            if (dom.audioPlayer.duration) {
                const pct = parseFloat(e.target.value);
                const targetTime = (pct / 100) * dom.audioPlayer.duration;
                dom.audioPlayer.currentTime = targetTime;

                if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                    state.ws.send(JSON.stringify({
                        type: 'playback_time',
                        current_time: targetTime
                    }));
                }
            }
        };
    }

    // Sync mode toggle (word vs verse)
    if (dom.btnSyncMode) {
        const savedSyncMode = localStorage.getItem('karaoke_sync_mode');
        if (savedSyncMode === 'verse') {
            state.syncMode = 'verse';
        }
        updateSyncModeButton();

        dom.btnSyncMode.onclick = () => {
            state.syncMode = state.syncMode === 'word' ? 'verse' : 'word';
            localStorage.setItem('karaoke_sync_mode', state.syncMode);
            updateSyncModeButton();
        };
    }
}

function updatePitchUI() {
    if (!dom.pitchValue) return;
    if (state.currentTranspose === 0) {
        dom.pitchValue.innerText = 'Normal';
    } else {
        dom.pitchValue.innerText = (state.currentTranspose > 0 ? '+' : '') + state.currentTranspose;
    }
}

function updateSpeedUI() {
    if (!dom.speedValue) return;
    dom.speedValue.innerText = state.currentSpeed.toFixed(2) + 'x';
}

function updateSyncModeButton() {
    if (!dom.btnSyncMode) return;
    if (state.syncMode === 'verse') {
        dom.btnSyncMode.innerHTML = `${iconSvg('sync-verse')}<span>Verso</span>`;
        dom.btnSyncMode.title = 'Sincronia por verso — Clique para alternar para palavras';
        dom.btnSyncMode.classList.add('btn-sync-mode--active');
    } else {
        dom.btnSyncMode.innerHTML = `${iconSvg('sync-word')}<span>Palavra</span>`;
        dom.btnSyncMode.title = 'Sincronia por palavra — Clique para alternar para verso';
        dom.btnSyncMode.classList.remove('btn-sync-mode--active');
    }
}

function setScoreMode(mode) {
    const btn = dom.btnScoreMode;
    if (!btn) return;
    const normalized = mode === 'words' ? 'words' : 'timing';
    btn.setAttribute('data-mode', normalized);
    if (normalized === 'words') {
        btn.innerHTML = `${iconSvg('score-words')}<span>Só palavras</span>`;
        btn.title = 'Pontuação: apenas palavras acertadas — Clique para incluir o tempo';
    } else {
        btn.innerHTML = `${iconSvg('metronome')}<span>Palavras + tempo</span>`;
        btn.title = 'Pontuação: palavras + tempo correto — Clique para pontuar só palavras';
    }
    btn.classList.toggle('btn-score-mode--active', normalized === 'words');
    localStorage.setItem('karaoke_scoring_mode', normalized);
}

