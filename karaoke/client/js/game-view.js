import { state } from './state.js';
import { dom } from './dom.js';
import { myRoom } from './config.js';
import { showToast } from './toast.js';
import { getMicrophoneStream } from './mic-stream.js';
import { updateSyncDisplay, startTimeSync } from './sync.js';
import { updateMicStatusPanel } from './mic-status.js';
import { connectDisplayWebSocket } from './ws-display.js';

export function resetGameState() {
    if (state.transcriptionActiveTimer) {
        clearTimeout(state.transcriptionActiveTimer);
        state.transcriptionActiveTimer = null;
    }
    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }
    if (state.audioContext) {
        if (state.audioContext.state !== 'closed') {
            state.audioContext.close();
        }
        state.audioContext = null;
    }
    if (state.animationId) {
        cancelAnimationFrame(state.animationId);
        state.animationId = null;
    }
    state.isSingingActive = false;
    state.isOutroActive = false;
    const outroOverlay = document.getElementById('outro-overlay');
    if (outroOverlay) outroOverlay.style.display = 'none';
    const silenceOverlay = document.getElementById('silence-overlay');
    if (silenceOverlay) silenceOverlay.style.display = 'none';
    dom.audioPlayer.pause();
    dom.audioPlayer.src = '';

    document.getElementById('seg-score').innerText = '0%';
    const statsSyncVal = document.getElementById('stats-sync-value');
    if (statsSyncVal) statsSyncVal.innerText = '0ms';

    const progFill = document.getElementById('song-progress-fill');
    if (progFill) progFill.style.width = '0%';
    const timeCurrent = document.getElementById('song-time-current');
    if (timeCurrent) timeCurrent.innerText = '0:00';
    const timeRemaining = document.getElementById('song-time-remaining');
    if (timeRemaining) timeRemaining.innerText = '-0:00';

    const transText = document.getElementById('transcription-text');
    if (transText) {
        transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Aguardando canto...]</span>';
    }

    document.getElementById('score-progress-fill').style.width = '0%';
    document.getElementById('score-percentage-text').innerText = '0%';
    document.getElementById('instrumental-pause-container').style.display = 'none';

    const verseContainer = document.getElementById('verse-progress-container');
    const verseFill = document.getElementById('verse-progress-fill');
    if (verseContainer && verseFill) {
        verseFill.style.width = '0%';
        verseContainer.style.opacity = '0';
    }

    if (silenceOverlay) {
        silenceOverlay.style.display = 'none';
        document.getElementById('silence-progress-fill').style.width = '0%';
    }

    document.getElementById('line-prev').innerHTML = '';
    document.getElementById('line-curr').innerHTML = '';
    document.getElementById('line-next').innerHTML = '';

    dom.btnStart.style.display = 'inline-block';
    dom.btnStart.disabled = false;
    dom.btnStart.innerText = 'INICIAR CANTO';
    dom.btnExit.style.display = 'none';
    document.getElementById('sync-controls').style.display = 'flex';

    state.selectedSongId = null;
    state.currentSegments = null;
    state.currentSegmentData = null;
    state.lastSegmentLyricsTimed = null;
    state.syncOffset = 0;
    state.isFirstSegment = true;
    state.totalPauseDuration = 0;
    updateSyncDisplay();

    dom.gameArea.style.display = 'none';
    dom.selectionArea.style.display = 'block';

    showToast("Retornou à lista de músicas", "info");
    connectDisplayWebSocket();
}

export async function startKaraoke() {
    state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const sampleRate = state.audioContext.sampleRate;

    let stream = null;
    if (state.localStreamForced || !state.isMobileMicrophoneConnected) {
        try {
            stream = await getMicrophoneStream();
        } catch (err) {
            console.warn("Sem microfone local detectado. Continuando apenas para reprodução...", err);
            if (!state.isMobileMicrophoneConnected) {
                showToast("Modo som de fundo ativo (sem microfone local)", "warning");
            }
        }
    }

    if (state.ws) {
        try {
            state.ws.onclose = null;
            state.ws.close();
        } catch (e) { }
        state.ws = null;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${myRoom}?role=display&song_id=${state.selectedSongId}`;
    state.ws = new WebSocket(wsUrl);
    state.ws.binaryType = 'arraybuffer';

    state.ws.onopen = () => {
        state.ws.send(JSON.stringify({ type: "client_info", sample_rate: sampleRate }));
        state.isFirstSegment = true;
        state.currentSegmentData = null;
        dom.audioPlayer.play();
        startTimeSync();
    };

    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };

    if (stream) {
        await state.audioContext.audioWorklet.addModule('/js/worklets/audio-processor.js');
        const source = state.audioContext.createMediaStreamSource(stream);
        const processor = new AudioWorkletNode(state.audioContext, 'audio-processor');

        processor.port.onmessage = (event) => {
            if (state.ws && state.ws.readyState === WebSocket.OPEN && state.isSingingActive) {
                state.ws.send(event.data);
            }
        };

        source.connect(processor);
        processor.connect(state.audioContext.destination);
    }

    dom.btnStart.style.display = 'none';
    dom.btnExit.style.display = 'inline-block';
    document.getElementById('sync-controls').style.display = 'flex';
}

export function handleServerMessage(data) {
    if (data.type === 'pairing_status') {
        const pairingStatusText = document.getElementById('pairing-status-text');
        const pairingStatusDot = document.getElementById('pairing-status-dot');

        if (data.status === 'paired') {
            state.isMobileMicrophoneConnected = true;
            updateMicStatusPanel();
            if (pairingStatusText) {
                pairingStatusText.innerHTML = `✅ <span style="color: #10b981; font-weight: 800;">Celular conectado com sucesso!</span>`;
            }
            if (pairingStatusDot) {
                pairingStatusDot.style.background = '#10b981';
                pairingStatusDot.style.boxShadow = '0 0 10px #10b981';
            }
            showToast("Microfone sem fio pareado e ativo!", "success");
        } else if (data.status === 'unpaired') {
            state.isMobileMicrophoneConnected = false;
            updateMicStatusPanel();
            if (pairingStatusText) {
                pairingStatusText.innerText = "Aguardando conexão do celular...";
            }
            if (pairingStatusDot) {
                pairingStatusDot.style.background = 'var(--dim)';
                pairingStatusDot.style.boxShadow = 'none';
            }
            showToast("Microfone sem fio desconectado.", "warning");
        }
    }
    else if (data.type === 'singing_state') {
        state.isSingingActive = data.active;
        const transText = document.getElementById('transcription-text');
        if (transText && !state.transcriptionActiveTimer) {
            transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
        }
    }
    else if (data.type === 'outro_start') {
        state.isOutroActive = true;
        state.outroStartPlayerTime = dom.audioPlayer.currentTime;
        state.outroTotalDuration = Math.max(1, dom.audioPlayer.duration - state.outroStartPlayerTime);

        const outroOverlay = document.getElementById('outro-overlay');
        if (outroOverlay) outroOverlay.style.display = 'flex';
        const silenceOverlay = document.getElementById('silence-overlay');
        if (silenceOverlay) silenceOverlay.style.display = 'none';

        const transText = document.getElementById('transcription-text');
        if (transText) {
            transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--accent); font-weight: 700;">[Show Finalizado! 🎸]</span>';
        }
    }
    else if (data.type === 'segment_start') {
        if (!state.transcriptionActiveTimer) {
            const transText = document.getElementById('transcription-text');
            if (transText) {
                transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Solo Instrumental...]</span>';
            }
        }
        renderLyrics(data);
        startHighlightLoop();
    } else if (data.type === 'segment_result') {
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
                if (document.getElementById('game-area').style.display === 'block') {
                    transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                }
            }, 3500);
        } else {
            transText.innerHTML = '<strong>Ouvi:</strong> <span style="color: var(--dim);">[Silêncio ou Incompreensível]</span>';
            if (state.transcriptionActiveTimer) clearTimeout(state.transcriptionActiveTimer);
            state.transcriptionActiveTimer = setTimeout(() => {
                state.transcriptionActiveTimer = null;
                if (document.getElementById('game-area').style.display === 'block') {
                    transText.innerHTML = `<strong>Ouvi:</strong> <span style="color: var(--dim);">${state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]'}</span>`;
                }
            }, 3500);
        }

        const val = parseFloat(data.total_score) || 0;
        document.getElementById('score-progress-fill').style.width = val + '%';
        document.getElementById('score-percentage-text').innerText = val.toFixed(1) + '%';
    } else if (data.type === 'game_over') {
        dom.audioPlayer.pause();
        showGameOverModal(parseFloat(data.total_score) || 0);
    }
}

export function showGameOverModal(finalScore) {
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

    modal.style.display = 'flex';

    document.getElementById('btn-restart-game').onclick = () => {
        document.getElementById('game-over-modal').style.display = 'none';
        resetGameState();
    };
}

export function renderLyrics(data) {
    const virtualTime = dom.audioPlayer.currentTime + state.syncOffset;
    const pauseTime = data.sing_start - virtualTime;

    if (pauseTime > 1.0) {
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
        return;
    }

    const linePrev = document.getElementById('line-prev');
    const lineCurr = document.getElementById('line-curr');
    const lineNext = document.getElementById('line-next');

    linePrev.classList.add('fading');
    lineCurr.classList.add('fading');
    lineNext.classList.add('fading');

    setTimeout(() => {
        state.lastSegmentLyricsTimed = state.currentSegmentData ? state.currentSegmentData.lyrics_timed : null;
        state.currentSegmentData = data;
        updateLyricsDOM(data);

        linePrev.classList.remove('fading');
        lineCurr.classList.remove('fading');
        lineNext.classList.remove('fading');
    }, 150);
}

export function updateLyricsDOM(data) {
    dom.prevLyricsDisplay.innerText = data.prev_lyrics || "";
    dom.nextLyricsDisplay.innerText = data.next_lyrics || "";

    dom.lyricsDisplay.innerHTML = '';
    data.lyrics_timed.forEach((item, idx) => {
        const span = document.createElement('span');
        span.className = 'word';
        span.innerText = item.word + ' ';
        span.id = `word-${idx}`;
        dom.lyricsDisplay.appendChild(span);
    });
}

export function startHighlightLoop() {
    if (state.animationId) cancelAnimationFrame(state.animationId);

    function update() {
        const audioPlayer = dom.audioPlayer;
        if (audioPlayer.duration) {
            const cur = audioPlayer.currentTime;
            const dur = audioPlayer.duration;
            const pct = Math.max(0, Math.min(100, (cur / dur) * 100));

            const formatTime = (secs) => {
                const m = Math.floor(secs / 60);
                const s = Math.floor(secs % 60);
                return `${m}:${s < 10 ? '0' : ''}${s}`;
            };

            const progFill = document.getElementById('song-progress-fill');
            if (progFill) progFill.style.width = pct + '%';
            const timeCurrent = document.getElementById('song-time-current');
            if (timeCurrent) timeCurrent.innerText = formatTime(cur);
            const timeRemaining = document.getElementById('song-time-remaining');
            if (timeRemaining) timeRemaining.innerText = '-' + formatTime(Math.max(0, dur - cur));
        }

        if (state.isOutroActive && audioPlayer.duration) {
            const outroOverlay = document.getElementById('outro-overlay');
            if (outroOverlay) outroOverlay.style.display = 'flex';

            const cur = audioPlayer.currentTime;
            const elapsed = cur - state.outroStartPlayerTime;
            const remaining = Math.max(0, audioPlayer.duration - cur);

            const pct = Math.max(0, Math.min(100, (elapsed / state.outroTotalDuration) * 100));

            const outroFill = document.getElementById('outro-progress-fill');
            if (outroFill) outroFill.style.width = pct + '%';

            const outroText = document.getElementById('outro-timer-text');
            if (outroText) outroText.innerText = `Finalizando em ${remaining.toFixed(1)}s...`;

            state.animationId = requestAnimationFrame(update);
            return;
        }

        if (!state.currentSegmentData) {
            state.animationId = requestAnimationFrame(update);
            return;
        }

        const virtualTime = audioPlayer.currentTime + state.syncOffset;
        const relativeTime = virtualTime - state.currentSegmentData.sing_start;

        const silenceOverlay = document.getElementById('silence-overlay');
        const pauseContainer = document.getElementById('instrumental-pause-container');

        if (state.totalPauseDuration > 1.0) {
            const remainingTime = state.pauseStartTarget - virtualTime;

            if (remainingTime > 0) {
                if (pauseContainer) pauseContainer.style.display = 'none';
                if (silenceOverlay) {
                    silenceOverlay.style.display = 'flex';
                    const fill = document.getElementById('silence-progress-fill');
                    const text = document.getElementById('silence-timer-text');
                    const pct = Math.max(0, Math.min(100, (remainingTime / state.totalPauseDuration) * 100));
                    if (fill) fill.style.width = pct + '%';
                    if (text) text.innerText = remainingTime.toFixed(1) + 's';
                }
            } else {
                if (silenceOverlay) silenceOverlay.style.display = 'none';
                state.totalPauseDuration = 0;
                state.pauseStartTarget = 0;
            }
        } else {
            if (silenceOverlay) silenceOverlay.style.display = 'none';
            if (pauseContainer) pauseContainer.style.display = 'none';
        }

        const verseContainer = document.getElementById('verse-progress-container');
        const verseFill = document.getElementById('verse-progress-fill');
        if (verseContainer && verseFill) {
            const segStart = state.currentSegmentData.sing_start;
            const segEnd = state.currentSegmentData.sing_end;
            const duration = segEnd - segStart;

            if (virtualTime >= segStart && virtualTime <= segEnd && duration > 0) {
                const pct = Math.max(0, Math.min(100, ((virtualTime - segStart) / duration) * 100));
                verseFill.style.width = pct + '%';
                verseContainer.style.opacity = '1';
            } else if (virtualTime > segEnd) {
                verseFill.style.width = '100%';
                verseContainer.style.opacity = '0.5';
            } else {
                verseFill.style.width = '0%';
                verseContainer.style.opacity = '0';
            }
        }

        state.currentSegmentData.lyrics_timed.forEach((item, idx) => {
            const el = document.getElementById(`word-${idx}`);
            if (!el) return;

            if (relativeTime >= item.expected_start) {
                el.classList.add('passed');
                el.classList.remove('active');
            } else {
                el.classList.remove('passed');
            }

            const nextItem = state.currentSegmentData.lyrics_timed[idx + 1];
            if (relativeTime >= item.expected_start && (!nextItem || relativeTime < nextItem.expected_start)) {
                el.classList.add('active');
                el.classList.remove('passed');
            } else {
                if (relativeTime < item.expected_start) el.classList.remove('active');
            }
        });

        state.animationId = requestAnimationFrame(update);
    }
    update();
}
