import { state, setAppState } from './state.js';
import { dom } from './dom.js';
import { myRoom } from './config.js';
import { showToast } from './toast.js';
import { AudioLifecycleManager } from './audio-lifecycle-manager.js';
import { updateSyncDisplay, startTimeSync } from './sync.js';
import { updateMicStatusPanel } from './mic-status.js';
import { connectDisplayWebSocket } from './ws-display.js';

export async function resetGameState() {
    const gameOverModal = document.getElementById('game-over-modal');
    if (gameOverModal) gameOverModal.removeAttribute('data-open');

    if (state.slideTransitionCleanup) {
        state.slideTransitionCleanup();
    }
    if (state.transcriptionActiveTimer) {
        clearTimeout(state.transcriptionActiveTimer);
        state.transcriptionActiveTimer = null;
    }
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
        dom.songProgressSlider.style.background = 'rgba(255, 255, 255, 0.05)';
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
        transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Aguardando canto...]</span>';
    }

    const scoreFill = document.getElementById('score-progress-fill');
    if (scoreFill) {
        scoreFill.style.height = '0%';
        scoreFill.style.width = '';
    }
    document.getElementById('score-percentage-text').innerText = '0%';

    const perfBorder = document.getElementById('perf-border-overlay');
    if (perfBorder) {
        perfBorder.className = 'perf-border-idle';
    }

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

    hideMpScoreBars();

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

    showToast("Retornou à lista de músicas", "info");
    connectDisplayWebSocket();
}

export async function startKaraoke() {
    const capturedSongId = state.selectedSongId;

    // Carrega o segments.json inteiro no front antes de iniciar
    try {
        const resp = await fetch(`/api/songs/${capturedSongId}`);
        if (!resp.ok) throw new Error("Falha ao carregar os segmentos da música");
        const songData = await resp.json();
        state.currentSegments = songData.segments;
        console.log(`Carregados ${state.currentSegments.length} segmentos para a música localmente.`);
    } catch (err) {
        console.error("Erro ao pré-carregar os segmentos:", err);
        showToast("Erro ao carregar os segmentos da música do servidor.", "error");
        return;
    }

    const captureMic = !!(state.localStreamForced || !state.isMobileMicrophoneConnected);

    if (state.audioManager) {
        await state.audioManager.destroy();
        state.audioManager = null;
    }

    state.audioManager = new AudioLifecycleManager({
        captureMic: captureMic,
        mediaElement: dom.audioPlayer,
        onAudioChunk: (data) => {
            if (state.ws && state.ws.readyState === WebSocket.OPEN && state.isSingingActive) {
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
                mediaElement: dom.audioPlayer
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

    const mode = dom.mpGameMode.value;
    const activeList = [];
    const slots = [dom.slotP1, dom.slotP2, dom.slotP3, dom.slotP4];
    const numSlots = (mode === 'solo') ? 1 : ((mode === '1v1') ? 2 : ((mode === '1v1v1') ? 3 : 4));

    for (let i = 0; i < numSlots; i++) {
        if (slots[i] && slots[i].value) {
            activeList.push(slots[i].value);
        }
    }

    state.activePlayers = activeList;
    state.gameMode = mode;

    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connectGameWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/room/${myRoom}?role=display&song_id=${capturedSongId}`;
        state.ws = new WebSocket(wsUrl);
        state.ws.binaryType = 'arraybuffer';

        state.ws.onopen = () => {
            reconnectAttempts = 0;

            state.ws.send(JSON.stringify({ type: "client_info", sample_rate: sampleRate }));
            state.ws.send(JSON.stringify({
                type: "start_game",
                game_mode: mode,
                active_players: activeList
            }));

            state.isFirstSegment = true;
            state.currentSegmentData = null;
            dom.audioPlayer.play();
            startTimeSync();
            setAppState('singing');
            startHighlightLoop();
        };

        state.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        };

        state.ws.onclose = () => {
            console.warn("Game WebSocket fechado. Tentando reconectar...");
            if (state.currentAppState === 'idle' || state.currentAppState === 'game-over') return;
            if (reconnectAttempts >= maxReconnectAttempts) {
                console.error("Número máximo de tentativas de reconexão atingido. Abortando jogo.");
                resetGameState();
                return;
            }
            reconnectAttempts++;
            const delay = Math.min(1000 * reconnectAttempts, 5000);
            console.log(`Tentativa de reconexão ${reconnectAttempts}/${maxReconnectAttempts} em ${delay}ms...`);
            setTimeout(connectGameWebSocket, delay);
        };

        state.ws.onerror = (err) => {
            console.error("Erro no WebSocket do jogo:", err);
        };
    }

    connectGameWebSocket();

    dom.audioPlayer.playbackRate = state.currentSpeed;
}

const DISPLAY_HANDLERS = {
    players_update(data, context) {
        const { dom } = context;
        if (dom.mpConnectedCount) dom.mpConnectedCount.innerText = data.players.length;
        if (dom.mpQueueCount) dom.mpQueueCount.innerText = data.queue_count;

        // Repopula os slots
        const selects = [dom.slotP1, dom.slotP2, dom.slotP3, dom.slotP4];
        selects.forEach((select, idx) => {
            if (!select) return;
            const prevVal = select.value;
            select.innerHTML = '';

            // Se não for o primeiro slot, permite que fique vazio
            if (idx > 0) {
                const optEmpty = document.createElement('option');
                optEmpty.value = '';
                optEmpty.innerText = '-- Vazio --';
                select.appendChild(optEmpty);
            }

            // Opção para o microfone local do PC
            const optPC = document.createElement('option');
            optPC.value = 'PC_Local';
            optPC.innerText = '💻 PC Local Mic';
            select.appendChild(optPC);

            // Adiciona os jogadores conectados (celulares)
            data.players.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p;
                opt.innerText = p;
                select.appendChild(opt);
            });

            // Tenta restaurar o valor selecionado anteriormente
            if (prevVal === 'PC_Local' || data.players.includes(prevVal)) {
                select.value = prevVal;
            } else {
                if (idx === 0) {
                    if (data.players.length > 0) {
                        select.value = data.players[0];
                    } else {
                        select.value = 'PC_Local';
                    }
                } else {
                    if (idx < data.players.length) {
                        select.value = data.players[idx];
                    } else {
                        select.value = '';
                    }
                }
            }
        });
    },
    pairing_status(data, context) {
        const { state } = context;
        const pairingStatusText = document.getElementById('pairing-status-text');
        const pairingStatusDot = document.getElementById('pairing-status-dot');

        if (data.status === 'paired') {
            state.isMobileMicrophoneConnected = true;
            updateMicStatusPanel();
            if (pairingStatusText) {
                pairingStatusText.innerHTML = `✅ <span style="color: #10b981; font-weight: 800;">Celular conectado com sucesso!</span>`;
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
            showToast("Microfone sem fio desconectado.", "warning");
        }
    },
    singing_state(data, context) {
        const { state } = context;
        if (state.currentSegments) return;
        state.isSingingActive = data.active;
        const transText = document.getElementById('transcription-text');
        if (transText && !state.transcriptionActiveTimer) {
            transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
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
            transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--accent); font-weight: 700;">[Show Finalizado! 🎸]</span>';
        }
    },
    segment_start(data, context) {
        const { state } = context;
        if (state.currentSegments) return;
        if (!state.transcriptionActiveTimer) {
            const transText = document.getElementById('transcription-text');
            if (transText) {
                transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Solo Instrumental...]</span>';
            }
        }
        renderLyrics(data);
        startHighlightLoop();
    },
    segment_result(data, context) {
        const { state } = context;
        document.getElementById('seg-score').innerText = data.score + '%';
        const transText = document.getElementById('transcription-text');

        if (data.transcription && data.transcription.trim()) {
            const words = data.transcription.split(/\s+/);
            transText.innerHTML = '<strong>Ouvi:</strong> ';

            const expectedNormalized = state.lastSegmentLyricsTimed
                ? state.lastSegmentLyricsTimed.map(w => w.word.toLowerCase().replace(/[^\w\s]/g, '').trim())
                : [];

            words.forEach(word => {
                const cleanWord = word.toLowerCase().replace(/[^\w\s]/g, '').trim();
                const isMatch = expectedNormalized.includes(cleanWord);

                const span = document.createElement('span');
                span.innerText = word + ' ';
                span.style.fontWeight = '700';
                if (isMatch) {
                    span.style.color = '#22c55e';
                    span.style.textShadow = '0 0 10px rgba(34, 197, 94, 0.4)';
                } else {
                    span.style.color = '#ef4444';
                    span.style.textShadow = '0 0 10px rgba(239, 68, 68, 0.4)';
                }
                transText.appendChild(span);
            });

            if (state.transcriptionActiveTimer) clearTimeout(state.transcriptionActiveTimer);
            state.transcriptionActiveTimer = setTimeout(() => {
                state.transcriptionActiveTimer = null;
                if (state.currentAppState !== 'idle') {
                    transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                }
            }, 3500);
        } else {
            transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Silêncio ou Incompreensível]</span>';
            if (state.transcriptionActiveTimer) clearTimeout(state.transcriptionActiveTimer);
            state.transcriptionActiveTimer = setTimeout(() => {
                state.transcriptionActiveTimer = null;
                if (state.currentAppState !== 'idle') {
                    transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                }
            }, 3500);
        }

        const val = parseFloat(data.total_score) || 0;
        const scoreFill = document.getElementById('score-progress-fill');
        if (scoreFill) {
            scoreFill.style.height = val + '%';
        }
        document.getElementById('score-percentage-text').innerText = val.toFixed(1) + '%';

        // Update performance border overlay based on the last segment score
        const lastSegmentScore = parseFloat(data.score) || 0;
        const perfBorder = document.getElementById('perf-border-overlay');
        if (perfBorder) {
            perfBorder.className = ''; // Reset classes
            if (lastSegmentScore >= 85) {
                perfBorder.className = 'perf-border-good';
            } else if (lastSegmentScore >= 70) {
                perfBorder.className = 'perf-border-ok';
            } else {
                perfBorder.className = 'perf-border-poor';
            }

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
            const activeList = state.activePlayers;
            const mode = state.gameMode;
            const slots = ['p1', 'p2', 'p3', 'p4'];
            
            const expectedNormalized = state.lastSegmentLyricsTimed
                ? state.lastSegmentLyricsTimed.map(w => w.word.toLowerCase().replace(/[^\w\s]/g, '').trim())
                : [];

            if (mode === '2v2') {
                const p1Val = (data.player_scores[activeList[0]]?.total_score || 0);
                const p2Val = (data.player_scores[activeList[1]]?.total_score || 0);
                const teamA = (p1Val + p2Val) / 2;
                
                const p3Val = (data.player_scores[activeList[2]]?.total_score || 0);
                const p4Val = (data.player_scores[activeList[3]]?.total_score || 0);
                const teamB = (p3Val + p4Val) / 2;
                
                const barA = document.getElementById('mp-score-bar-p1');
                if (barA) {
                    barA.querySelector('.mp-player-pct').innerText = teamA.toFixed(1) + "%";
                    barA.querySelector('.mp-progress-fill').style.width = teamA + "%";
                    
                    const transDiv = barA.querySelector('.mp-player-transcription');
                    if (transDiv) {
                        transDiv.innerHTML = '';
                        const p1Name = activeList[0];
                        const p2Name = activeList[1];
                        const t1 = data.player_scores[p1Name]?.transcription || '';
                        const t2 = data.player_scores[p2Name]?.transcription || '';
                        
                        if (t1 || t2) {
                            const d1 = document.createElement('div');
                            d1.style.fontSize = '0.8rem';
                            d1.innerHTML = `<strong>${p1Name}:</strong> `;
                            renderTranscriptionInto(d1, t1, expectedNormalized, false);
                            transDiv.appendChild(d1);

                            const d2 = document.createElement('div');
                            d2.style.fontSize = '0.8rem';
                            d2.innerHTML = `<strong>${p2Name}:</strong> `;
                            renderTranscriptionInto(d2, t2, expectedNormalized, false);
                            transDiv.appendChild(d2);
                        } else {
                            transDiv.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Silêncio]</span>';
                        }
                    }
                }
                const barB = document.getElementById('mp-score-bar-p2');
                if (barB) {
                    barB.querySelector('.mp-player-pct').innerText = teamB.toFixed(1) + "%";
                    barB.querySelector('.mp-progress-fill').style.width = teamB + "%";

                    const transDiv = barB.querySelector('.mp-player-transcription');
                    if (transDiv) {
                        transDiv.innerHTML = '';
                        const p3Name = activeList[2];
                        const p4Name = activeList[3];
                        const t3 = data.player_scores[p3Name]?.transcription || '';
                        const t4 = data.player_scores[p4Name]?.transcription || '';
                        
                        if (t3 || t4) {
                            const d3 = document.createElement('div');
                            d3.style.fontSize = '0.8rem';
                            d3.innerHTML = `<strong>${p3Name}:</strong> `;
                            renderTranscriptionInto(d3, t3, expectedNormalized, false);
                            transDiv.appendChild(d3);

                            const d4 = document.createElement('div');
                            d4.style.fontSize = '0.8rem';
                            d4.innerHTML = `<strong>${p4Name}:</strong> `;
                            renderTranscriptionInto(d4, t4, expectedNormalized, false);
                            transDiv.appendChild(d4);
                        } else {
                            transDiv.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Silêncio]</span>';
                        }
                    }
                }
            } else {
                activeList.forEach((name, idx) => {
                    const key = slots[idx];
                    const bar = document.getElementById(`mp-score-bar-${key}`);
                    if (bar && data.player_scores[name]) {
                        const pVal = data.player_scores[name].total_score;
                        bar.querySelector('.mp-player-pct').innerText = pVal.toFixed(1) + "%";
                        const fill = bar.querySelector('.mp-progress-fill') || bar.querySelector('.mp-progress-fill-vertical');
                        if (fill) {
                            if (fill.classList.contains('mp-progress-fill-vertical')) {
                                fill.style.height = pVal + "%";
                            } else {
                                fill.style.width = pVal + "%";
                            }
                        }

                        const transDiv = bar.querySelector('.mp-player-transcription');
                        if (transDiv) {
                            renderTranscriptionInto(transDiv, data.player_scores[name].transcription || '', expectedNormalized, true);
                        }
                    }
                });
            }
            
            // Clear existing multiplayer border fade-out timers if any
            if (state.mpBorderTimers) {
                state.mpBorderTimers.forEach(t => clearTimeout(t));
                state.mpBorderTimers = [];
            } else {
                state.mpBorderTimers = [];
            }

            // Atualiza bordas dos cards dos jogadores
            activeList.forEach((name, idx) => {
                const key = slots[idx];
                const bar = document.getElementById(`mp-score-bar-${key}`);
                if (bar && data.player_scores[name]) {
                    const scoreVal = data.player_scores[name].score;
                    bar.classList.remove('mp-score-bar--good', 'mp-score-bar--ok', 'mp-score-bar--poor');
                    if (scoreVal >= 85) {
                        bar.classList.add('mp-score-bar--good');
                    } else if (scoreVal >= 70) {
                        bar.classList.add('mp-score-bar--ok');
                    } else {
                        bar.classList.add('mp-score-bar--poor');
                    }
                }
            });

            // Schedule fade out of borders and transcriptions after 2 seconds
            const fadeTimer = setTimeout(() => {
                activeList.forEach((name, idx) => {
                    const key = slots[idx];
                    const bar = document.getElementById(`mp-score-bar-${key}`);
                    if (bar) {
                        bar.classList.remove('mp-score-bar--good', 'mp-score-bar--ok', 'mp-score-bar--poor');
                        const transDiv = bar.querySelector('.mp-player-transcription');
                        if (transDiv) transDiv.innerHTML = '';
                    }
                });
            }, 2000);
            state.mpBorderTimers.push(fadeTimer);
        }
    },
    game_over(data, context) {
        const { dom } = context;
        dom.audioPlayer.pause();
        setAppState('game-over');
        showGameOverModal(parseFloat(data.total_score) || 0, data.player_scores);
    }
};

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
    let color = '#ef4444';
    let title = 'PRECISA PRATICAR!';

    if (finalScore >= 95) {
        rank = 'S'; color = '#fde047'; title = 'PERFORMANCE LENDÁRIA!';
    } else if (finalScore >= 85) {
        rank = 'A'; color = '#38bdf8'; title = 'EXCELENTE APRESENTAÇÃO!';
    } else if (finalScore >= 70) {
        rank = 'B'; color = '#22c55e'; title = 'BOM TRABALHO!';
    }

    rankBadge.innerText = rank;
    rankBadge.style.color = color;
    rankTitle.innerText = title;

    const sortedPlayers = playerScores ? Object.entries(playerScores).sort((a, b) => b[1] - a[1]) : [];
    const numPlayers = sortedPlayers.length;

    // Remove any old podium if present
    const oldPodium = document.getElementById('podium-area');
    if (oldPodium) {
        oldPodium.remove();
    }

    if (numPlayers > 1) {
        // Multiplayer: Show podium & hide solo rank components
        rankBadge.style.display = 'none';
        rankTitle.style.display = 'none';

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

        const formatName = (n) => n === "PC_Local" ? "💻 PC Local" : n;

        let columnsHtml = '';

        // 2nd Place
        if (second) {
            columnsHtml += `
                <div class="podium-col podium-2nd">
                    <span class="podium-name" title="${formatName(second[0])}">${formatName(second[0])}</span>
                    <span class="podium-score">${second[1].toFixed(1)}%</span>
                    <div class="podium-pedestal">2</div>
                </div>
            `;
        }

        // 1st Place
        if (first) {
            columnsHtml += `
                <div class="podium-col podium-1st">
                    <span class="podium-crown">👑</span>
                    <span class="podium-name" title="${formatName(first[0])}">${formatName(first[0])}</span>
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
                    <span class="podium-score">${third[1].toFixed(1)}%</span>
                    <div class="podium-pedestal">3</div>
                </div>
            `;
        } else if (second) {
            // Spacer to keep 1st place centered when only 2 players are on the podium
            columnsHtml += `<div class="podium-col" style="width: 95px; visibility: hidden;"></div>`;
        }

        podiumArea.innerHTML = `
            <div class="podium-columns">
                ${columnsHtml}
            </div>
            <div id="podium-extra-list" style="width: 100%; display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem;"></div>
        `;

        const extraList = document.getElementById('podium-extra-list');
        if (fourth && extraList) {
            const item = document.createElement('div');
            item.className = 'podium-extra-item';
            item.innerHTML = `<span>4º Lugar: ${formatName(fourth[0])}</span><span style="color: var(--highlight);">${fourth[1].toFixed(1)}%</span>`;
            extraList.appendChild(item);
        }
    } else {
        // Solo: Show solo rank components & hide podium
        rankBadge.style.display = 'block';
        rankTitle.style.display = 'block';
    }

    // Placar multiplayer no modal (only shown in solo or fallback)
    let breakdownDiv = document.getElementById('modal-mp-breakdown');
    if (!breakdownDiv) {
        breakdownDiv = document.createElement('div');
        breakdownDiv.id = 'modal-mp-breakdown';
        breakdownDiv.style.cssText = "margin-top: 1.5rem; text-align: left; display: flex; flex-direction: column; gap: 0.6rem; max-height: 180px; overflow-y: auto; padding-right: 0.5rem; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 1rem;";
        modalScore.parentNode.appendChild(breakdownDiv);
    }

    breakdownDiv.innerHTML = '';
    if (playerScores && Object.keys(playerScores).length > 0 && numPlayers <= 1) {
        breakdownDiv.style.display = 'flex';
        sortedPlayers.forEach(([name, score], idx) => {
            const item = document.createElement('div');
            item.style.cssText = "display: flex; justify-content: space-between; font-size: 0.95rem; font-weight: 700; color: #f8fafc; padding: 0.25rem 0;";
            let medal = "🎤";
            if (idx === 0) medal = "🥇";
            else if (idx === 1) medal = "🥈";
            else if (idx === 2) medal = "🥉";
            const displayName = name === "PC_Local" ? "💻 PC Local" : name;
            item.innerHTML = `<span>${medal} ${displayName}</span><span style="color: var(--highlight);">${score.toFixed(1)}%</span>`;
            breakdownDiv.appendChild(item);
        });
    } else {
        breakdownDiv.style.display = 'none';
    }

    modal.setAttribute('data-open', 'true');

    document.getElementById('btn-restart-game').onclick = () => {
        resetGameState();
    };
}

export function renderTranscriptionInto(container, transcription, expectedNormalized, showHeader = true) {
    if (!container) return;
    container.innerHTML = '';
    
    if (!transcription || !transcription.trim()) {
        container.innerHTML = showHeader ? '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Silêncio]</span>' : '<span style="color: var(--dim);">[Silêncio]</span>';
        return;
    }

    if (showHeader) {
        container.innerHTML = '<strong>Ouvi:</strong> ';
    }
    const words = transcription.split(/\s+/);
    words.forEach(word => {
        const cleanWord = word.toLowerCase().replace(/[^\w\s]/g, '').trim();
        const isMatch = expectedNormalized.includes(cleanWord);

        const span = document.createElement('span');
        span.innerText = word + ' ';
        span.style.fontWeight = '700';
        if (isMatch) {
            span.style.color = '#22c55e';
            span.style.textShadow = '0 0 10px rgba(34, 197, 94, 0.4)';
        } else {
            span.style.color = '#ef4444';
            span.style.textShadow = '0 0 10px rgba(239, 68, 68, 0.4)';
        }
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
        lineNext.textContent = data.lyrics || "";
    } else {
        lineNext.innerHTML = '';
        data.lyrics_timed.forEach((item, idx) => {
            const span = document.createElement('span');
            span.className = 'word';
            span.innerText = item.word + ' ';
            span.id = `word-${idx}`;
            lineNext.appendChild(span);
        });
    }

    // Set line-upcoming to show the incoming line next lyrics
    if (lineUpcoming) {
        lineUpcoming.innerText = data.next_lyrics || "";
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
        linePrev.innerText = data.prev_lyrics || "";
        if (state.syncMode === 'verse') {
            lineCurr.textContent = lineNext.textContent;
        } else {
            lineCurr.innerHTML = lineNext.innerHTML;
        }
        lineNext.innerText = data.next_lyrics || "";
        if (lineUpcoming) {
            lineUpcoming.innerText = data.upcoming_lyrics || "";
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
    dom.prevLyricsDisplay.innerText = data.prev_lyrics || "";
    dom.nextLyricsDisplay.innerText = data.next_lyrics || "";
    if (dom.upcomingLyricsDisplay) {
        dom.upcomingLyricsDisplay.innerText = data.upcoming_lyrics || "";
    }

    if (state.syncMode === 'verse') {
        dom.lyricsDisplay.textContent = data.lyrics || "";
    } else {
        dom.lyricsDisplay.innerHTML = '';
        data.lyrics_timed.forEach((item, idx) => {
            const span = document.createElement('span');
            span.className = 'word';
            span.innerText = item.word + ' ';
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
                    dom.songProgressSlider.style.background = `linear-gradient(to right, var(--accent) ${pct}%, rgba(255, 255, 255, 0.05) ${pct}%)`;
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

                        const segmentData = {
                            ...currentSeg,
                            prev_lyrics,
                            next_lyrics,
                            upcoming_lyrics
                        };

                        renderLyrics(segmentData);
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
                            transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
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
                                    transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">[Solo Instrumental...]</span>`;
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

                if (remainingTime > 1.0) {
                    const app = document.getElementById('app');
                    if (app) app.setAttribute('data-silence', 'true');
                    const fill = document.getElementById('silence-progress-fill');
                    const text = document.getElementById('silence-timer-text');
                    const pct = Math.max(0, Math.min(100, ((remainingTime - 1.0) / (state.totalPauseDuration - 1.0)) * 100));
                    if (fill) fill.style.width = pct + '%';
                    if (text) text.innerText = remainingTime.toFixed(1) + 's';
                } else {
                    const app = document.getElementById('app');
                    if (app) app.removeAttribute('data-silence');
                    state.totalPauseDuration = 0;
                    state.pauseStartTarget = 0;
                }
            } else {
                const app = document.getElementById('app');
                if (app) app.removeAttribute('data-silence');
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
}

export function initGameControls() {
    if (dom.mpGameMode) {
        dom.mpGameMode.onchange = () => {
            updatePlayerSlotsVisibility();
        };
        // Inicializa a exibição das slots
        updatePlayerSlotsVisibility();
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
            dom.songProgressSlider.style.background = `linear-gradient(to right, var(--accent) ${pct}%, rgba(255, 255, 255, 0.05) ${pct}%)`;

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
        dom.btnSyncMode.textContent = '📝';
        dom.btnSyncMode.title = 'Sincronia por verso — Clique para alternar para palavras';
        dom.btnSyncMode.style.background = 'rgba(56, 189, 248, 0.2)';
        dom.btnSyncMode.style.borderColor = 'var(--accent)';
    } else {
        dom.btnSyncMode.textContent = '🎯';
        dom.btnSyncMode.title = 'Sincronia por palavra — Clique para alternar para verso';
        dom.btnSyncMode.style.background = '';
        dom.btnSyncMode.style.borderColor = '';
    }
}

function updatePlayerSlotsVisibility() {
    if (!dom.mpGameMode) return;
    const mode = dom.mpGameMode.value;

    const setupContainer = dom.mpSetupContainer;
    if (setupContainer) {
        setupContainer.setAttribute('data-game-mode', mode);
    }

    const labelP1 = dom.slotBoxP1 ? dom.slotBoxP1.querySelector('label') : null;
    const labelP2 = dom.slotBoxP2 ? dom.slotBoxP2.querySelector('label') : null;
    const labelP3 = dom.slotBoxP3 ? dom.slotBoxP3.querySelector('label') : null;
    const labelP4 = dom.slotBoxP4 ? dom.slotBoxP4.querySelector('label') : null;

    if (mode === '2v2') {
        if (labelP1) labelP1.innerText = "Duo A - Jogador 1 (Bottom)";
        if (labelP2) labelP2.innerText = "Duo A - Jogador 2 (Top)";
        if (labelP3) labelP3.innerText = "Duo B - Jogador 3 (Left)";
        if (labelP4) labelP4.innerText = "Duo B - Jogador 4 (Right)";
    } else {
        if (labelP1) labelP1.innerText = "Jogador 1 (Bottom)";
        if (labelP2) labelP2.innerText = "Jogador 2 (Top)";
        if (labelP3) labelP3.innerText = "Jogador 3 (Left)";
        if (labelP4) labelP4.innerText = "Jogador 4 (Right)";
    }
}

function resetAndShowMpScoreBars(activeList, mode) {
    hideMpScoreBars();

    const slots = ['p1', 'p2', 'p3', 'p4'];
    const barMap = {
        p1: document.getElementById('mp-score-bar-p1'),
        p2: document.getElementById('mp-score-bar-p2'),
        p3: document.getElementById('mp-score-bar-p3'),
        p4: document.getElementById('mp-score-bar-p4')
    };

    if (mode === '2v2') {
        const formatName = (n) => n === "PC_Local" ? "💻 PC Local" : (n || 'Jogador');
        const nameA = formatName(activeList[0]) + " + " + formatName(activeList[1]);
        const nameB = formatName(activeList[2]) + " + " + formatName(activeList[3]);

        if (barMap.p1) {
            barMap.p1.setAttribute('data-active', 'true');
            barMap.p1.querySelector('.mp-player-name').innerText = "Duo A: " + nameA;
            barMap.p1.querySelector('.mp-player-pct').innerText = "0%";
            barMap.p1.querySelector('.mp-progress-fill').style.width = "0%";
        }
        if (barMap.p2) {
            barMap.p2.setAttribute('data-active', 'true');
            barMap.p2.querySelector('.mp-player-name').innerText = "Duo B: " + nameB;
            barMap.p2.querySelector('.mp-player-pct').innerText = "0%";
            barMap.p2.querySelector('.mp-progress-fill').style.width = "0%";
        }
    } else {
        activeList.forEach((name, idx) => {
            const key = slots[idx];
            const el = barMap[key];
            if (el) {
                el.setAttribute('data-active', 'true');
                const displayName = name === "PC_Local" ? "💻 PC Local" : name;
                el.querySelector('.mp-player-name').innerText = displayName;
                el.querySelector('.mp-player-pct').innerText = "0%";
                const fill = el.querySelector('.mp-progress-fill') || el.querySelector('.mp-progress-fill-vertical');
                if (fill) {
                    if (fill.classList.contains('mp-progress-fill-vertical')) {
                        fill.style.height = "0%";
                    } else {
                        fill.style.width = "0%";
                    }
                }
            }
        });
    }
}

function hideMpScoreBars() {
    ['p1', 'p2', 'p3', 'p4'].forEach(key => {
        const el = document.getElementById(`mp-score-bar-${key}`);
        if (el) {
            el.removeAttribute('data-active');
            el.classList.remove('mp-score-bar--good', 'mp-score-bar--ok', 'mp-score-bar--poor');
            const transDiv = el.querySelector('.mp-player-transcription');
            if (transDiv) transDiv.innerHTML = '';
        }
    });
}
