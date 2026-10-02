// Laço da letra na TV: a cada quadro lê o tempo da música e acende as palavras,
// troca de verso, move as barras de progresso e conta o fim dos solos.
import { state } from '../core/state.js';
import { dom } from '../core/dom.js';
import { isTvBrowser } from '../core/config.js';
import { turnOwner } from './turns.js';
import { sendPlayerEvent } from './game-events.js';
import { renderLyrics } from './lyrics-carousel.js';
import { followWord, followProgress } from './long-verse.js';
import { showHeardHint, listeningHint } from './transcription.js';
import { showTurn, setCountdown, setSilence, setSilenceProgress, setVerseProgress, setOutroProgress } from './hud.js';

// TV: temporizador fixo de ~15 quadros/s. O requestAnimationFrame do WebView da
// Google TV (TV Bro) dispara raramente: a letra acendia no fim do verso e o
// contador parava antes do fim da música.
const TV_FRAME_MS = 66;

const COUNTDOWN_SEC = 3;
// Barra do solo só com pelo menos 3 s dela + 3 s de contagem: menos que isso
// ela piscava na tela. Pausas mais curtas mostram só a contagem.
const SILENCE_BAR_MIN_SEC = 3;
// Pausa a partir da qual o palco mostra barra de solo ou contagem
const LONG_PAUSE_SEC = 3.0;

// Janela em que o verso conta como "cantando" (mostra "[Ouvindo...]")
const SINGING_PRE_BUFFER_SEC = 1.0;
const POST_SING_BUFFER_SEC = 0.5;

function scheduleLyricsFrame(fn) {
    return isTvBrowser ? setTimeout(fn, TV_FRAME_MS) : requestAnimationFrame(fn);
}

export function cancelLyricsFrame() {
    if (!state.animationId) return;
    if (isTvBrowser) clearTimeout(state.animationId);
    else cancelAnimationFrame(state.animationId);
    state.animationId = null;
}

function setTextIfChanged(el, text) {
    if (el && el.textContent !== text) el.textContent = text;
}

export function formatTime(secs) {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
}

export function paintProgressSlider(pct) {
    dom.songProgressSlider.style.background = `linear-gradient(to right, var(--accent) ${pct}%, var(--track) ${pct}%)`;
}

function showSongTime(cur, dur) {
    setTextIfChanged(document.getElementById('song-time-current'), formatTime(cur));
    setTextIfChanged(document.getElementById('song-time-remaining'), '-' + formatTime(Math.max(0, dur - cur)));
}

// Barra e tempo da música. Só mexe no DOM quando muda: cada escrita custa um repaint na TV.
function updateSongProgress(audio) {
    if (!audio.duration || state.isUserDraggingProgress) return;
    const cur = audio.currentTime;
    const dur = audio.duration;
    const pct = Math.round(Math.max(0, Math.min(100, (cur / dur) * 100)) * 10) / 10;
    if (dom.songProgressSlider && dom.songProgressSlider.dataset.pct !== String(pct)) {
        dom.songProgressSlider.dataset.pct = String(pct);
        dom.songProgressSlider.value = pct;
        paintProgressSlider(pct);
    }
    showSongTime(cur, dur);
}

// Fim da música depois do último verso. Retorna true enquanto estiver no fim.
function updateOutro(audio) {
    if (!state.isOutroActive || !audio.duration) return false;
    const cur = audio.currentTime;
    const elapsed = cur - state.outroStartPlayerTime;
    const pct = Math.max(0, Math.min(100, (elapsed / state.outroTotalDuration) * 100));
    setOutroProgress(pct, Math.max(0, audio.duration - cur));
    return true;
}

// Verso N com as linhas vizinhas que o carrossel mostra
function segmentWithNeighbors(segments, idx) {
    const lyricsAt = (i) => (segments[i] ? segments[i].lyrics : '');
    // Japonês: romaji das linhas vizinhas (undefined nos outros idiomas)
    const romajiAt = (i) => segments[i] && segments[i].lyrics_romaji;
    return {
        ...segments[idx],
        prev_lyrics: idx > 0 ? lyricsAt(idx - 1) : '',
        next_lyrics: lyricsAt(idx + 1),
        upcoming_lyrics: lyricsAt(idx + 2),
        prev_lyrics_romaji: romajiAt(idx - 1),
        next_lyrics_romaji: romajiAt(idx + 1),
        upcoming_lyrics_romaji: romajiAt(idx + 2),
    };
}

function setSingingActive(active, hint) {
    if (active === state.isSingingActive) return;
    state.isSingingActive = active;
    showHeardHint(hint || listeningHint());
}

// Troca de verso pelo relógio local (a letra inteira já veio no início)
function syncCurrentSegment(virtualTime) {
    const segments = state.currentSegments;
    if (!segments) return;
    let idx = segments.length;
    for (let i = 0; i < segments.length; i++) {
        if (virtualTime < segments[i].sing_end) {
            idx = i;
            break;
        }
    }

    if (idx < segments.length) {
        const seg = segments[idx];
        if (!state.currentSegmentData || state.currentSegmentData.id !== seg.id) {
            renderLyrics(segmentWithNeighbors(segments, idx));
            // gravação: quando a TV mostrou o verso e se o laço travou
            sendPlayerEvent('line', `${seg.id}|${Math.round(state.lyricsFrameGapMax)}`);
            state.lyricsFrameGapMax = 0;
            showTurn(turnOwner(segments, state.turnOrder, idx));
        }
        setSingingActive(
            seg.sing_start - SINGING_PRE_BUFFER_SEC <= virtualTime && virtualTime <= seg.sing_end + POST_SING_BUFFER_SEC
        );
    } else if (segments.length > 0 && !state.isOutroActive && state.isSingingActive) {
        // passou do último verso
        setSingingActive(false, '[Solo Instrumental...]');
    }
}

// Solo longo: barra até faltarem 3 s, depois a contagem 3… 2… 1
function updatePause(virtualTime) {
    if (!(state.totalPauseDuration > LONG_PAUSE_SEC)) {
        setSilence(false);
        setCountdown(null);
        return;
    }
    const remaining = state.pauseStartTarget - virtualTime;
    const showBar = state.totalPauseDuration >= COUNTDOWN_SEC + SILENCE_BAR_MIN_SEC;
    if (remaining > COUNTDOWN_SEC && !showBar) {
        setSilence(false);
        setCountdown(null);
    } else if (remaining > COUNTDOWN_SEC) {
        setSilence(true);
        setCountdown(null);
        const pct = Math.max(0, Math.min(100, ((remaining - COUNTDOWN_SEC) / (state.totalPauseDuration - COUNTDOWN_SEC)) * 100));
        setSilenceProgress(pct, remaining);
    } else if (remaining > 0.1) {
        // 3… 2… 1 por cima da próxima linha: depois de um solo muita gente entrava atrasada
        setSilence(false);
        setCountdown(Math.ceil(remaining));
    } else {
        setSilence(false);
        setCountdown(null);
        state.totalPauseDuration = 0;
        state.pauseStartTarget = 0;
    }
}

// Modo verso: a linha inteira acende. Modo palavra: passada, ativa ou por vir.
function highlightWords(segData, virtualTime) {
    const relativeTime = virtualTime - segData.sing_start;
    if (state.syncMode === 'verse') {
        const lineCurr = document.getElementById('line-curr');
        if (lineCurr) {
            lineCurr.classList.toggle('verse-active', relativeTime >= 0 && virtualTime <= segData.sing_end);
            followProgress(lineCurr, relativeTime / Math.max(0.1, segData.sing_end - segData.sing_start));
        }
        return;
    }
    if (!segData.lyrics_timed) return;
    segData.lyrics_timed.forEach((item, idx) => {
        const el = document.getElementById(`word-${idx}`);
        if (!el) return;
        const nextItem = segData.lyrics_timed[idx + 1];
        const reached = relativeTime >= item.expected_start;
        const active = reached && (!nextItem || relativeTime < nextItem.expected_start);
        el.classList.toggle('active', active);
        el.classList.toggle('passed', reached && !active);
        if (active) followWord(el.parentElement, el);  // verso comprido: a janela acompanha
    });
}

function frame() {
    // maior intervalo entre quadros desde o último verso (diagnóstico de TV)
    const now = performance.now();
    if (state.lyricsFrameAt) state.lyricsFrameGapMax = Math.max(state.lyricsFrameGapMax, now - state.lyricsFrameAt);
    state.lyricsFrameAt = now;

    const audio = dom.audioPlayer;
    updateSongProgress(audio);
    if (updateOutro(audio)) return;

    const virtualTime = audio.currentTime + state.syncOffset;
    syncCurrentSegment(virtualTime);

    const segData = state.currentSegmentData;
    if (!segData || typeof segData.sing_start !== 'number') return;

    updatePause(virtualTime);
    setVerseProgress(virtualTime, segData.sing_start, segData.sing_end);
    highlightWords(segData, virtualTime);
}

export function startHighlightLoop() {
    cancelLyricsFrame();
    state.lyricsFrameAt = 0;
    state.lyricsFrameGapMax = 0;

    function update() {
        try {
            frame();
        } catch (err) {
            console.error("Erro no loop de animação da letra:", err);
        } finally {
            if (state.currentAppState !== 'idle' && state.currentAppState !== 'game-over') {
                state.animationId = scheduleLyricsFrame(update);
            }
        }
    }
    update();
}
