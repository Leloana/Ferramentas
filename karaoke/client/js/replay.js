// "Ouvir minha apresentação": a voz gravada do cantor (recordings/<id>/<nome>.wav,
// já no tempo da música) tocando junto do instrumental, no fim de jogo.
import { state } from './state.js';

const BACKING_VOLUME = 0.55;
const MAX_DRIFT_SEC = 0.3;
const FIX_EVERY_MS = 2000;
const READY_TIMEOUT_MS = 15000;

// Resolve quando o áudio já pode tocar sem parar para carregar.
function ready(audio) {
    if (audio.readyState >= 3) return Promise.resolve();
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('áudio não carregou')), READY_TIMEOUT_MS);
        const ok = () => { clearTimeout(timer); resolve(); };
        audio.addEventListener('canplay', ok, { once: true });
        audio.addEventListener('error', () => { clearTimeout(timer); reject(new Error('erro no áudio')); }, { once: true });
        audio.load();
    });
}

// Parar não basta: o áudio pausado segue baixando e prende uma das ~6 conexões
// do navegador com o servidor; depois de alguns plays o próximo nunca carregava.
function release(audio) {
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
}

function stop() {
    const r = state.replay;
    if (!r) return;
    clearTimeout(r.endTimer);
    release(r.voice);
    release(r.backing);
    if (r.button) r.button.classList.remove('is-playing');
    if (r.onStop) r.onStop();
    state.replay = null;
}

export function stopReplay() {
    stop();
}

// Liga/desliga. `button` recebe .is-playing enquanto toca.
export function toggleReplay({ recordingId, player, songId, button, onStop }) {
    const current = state.replay;
    stop();
    if (current && current.player === player && current.recordingId === recordingId) return;

    const voice = new Audio(`/api/recordings/${encodeURIComponent(recordingId)}/audio/${encodeURIComponent(player)}`);
    const backing = new Audio(`/songs/${encodeURIComponent(songId)}/audio`);
    backing.volume = BACKING_VOLUME;
    voice.preload = 'auto';
    backing.preload = 'auto';
    const replay = { voice, backing, player, recordingId, button, onStop, lastFixAt: 0 };
    state.replay = replay;
    if (button) button.classList.add('is-playing');

    // A voz manda no relógio; o instrumental segue. Corrigir a cada 0,12 s com o
    // MP3 ainda carregando fazia o instrumental pular e travar no começo (verso
    // "cortado", fora do tempo até tudo carregar): só corrige desvio grande, com
    // os dois prontos, e no máximo a cada 2 s.
    voice.addEventListener('timeupdate', () => {
        if (backing.seeking || backing.readyState < 3 || voice.readyState < 3) return;
        const now = Date.now();
        if (now - replay.lastFixAt < FIX_EVERY_MS) return;
        if (Math.abs(backing.currentTime - voice.currentTime) > MAX_DRIFT_SEC) {
            replay.lastFixAt = now;
            backing.currentTime = voice.currentTime;
        }
    });
    const stopThis = () => { if (state.replay === replay) stop(); };
    voice.addEventListener('ended', stopThis);
    voice.addEventListener('error', stopThis);

    // só começa com os dois prontos para tocar, juntos do zero
    Promise.all([ready(voice), ready(backing)]).then(() => {
        if (state.replay !== replay) return;
        return Promise.all([voice.play(), backing.play()]);
    }).catch(() => { if (state.replay === replay) stop(); });
}

// Anotar versos: toca só um verso (voz + instrumental baixinho, para ouvir se
// entrei no tempo), com folga antes e depois. Tocar de novo no mesmo verso para.
const VERSE_BACKING_VOLUME = 0.3;
const VERSE_LEAD_SEC = 0.6;
const VERSE_TAIL_SEC = 0.8;

function seekTo(audio, t) {
    return new Promise((resolve) => {
        if (Math.abs(audio.currentTime - t) < 0.01) { resolve(); return; }
        audio.addEventListener('seeked', () => resolve(), { once: true });
        audio.currentTime = t;
    });
}

export function playVerse({ recordingId, player, songId, start, end, key, button, onStop }) {
    const current = state.replay;
    stop();
    if (current && current.verseKey === key) return;

    const voice = new Audio(`/api/recordings/${encodeURIComponent(recordingId)}/audio/${encodeURIComponent(player)}`);
    const backing = new Audio(songId ? `/songs/${encodeURIComponent(songId)}/audio` : '');
    backing.volume = VERSE_BACKING_VOLUME;
    voice.preload = 'auto';
    backing.preload = 'auto';
    const replay = { voice, backing, player, recordingId, button, onStop, verseKey: key, endTimer: 0 };
    state.replay = replay;
    if (button) button.classList.add('is-playing');
    const stopThis = () => { if (state.replay === replay) stop(); };
    voice.addEventListener('ended', stopThis);
    voice.addEventListener('error', stopThis);

    const from = Math.max(0, start - VERSE_LEAD_SEC);
    const durationMs = (Math.max(end, start + 1) + VERSE_TAIL_SEC - from) * 1000;
    const sources = songId ? [voice, backing] : [voice];
    Promise.all(sources.map(ready))
        .then(() => Promise.all(sources.map(a => seekTo(a, from))))
        .then(() => {
            if (state.replay !== replay) return;
            replay.endTimer = setTimeout(() => { if (state.replay === replay) stop(); }, durationMs);
            return Promise.all(sources.map(a => a.play()));
        })
        .catch(() => { if (state.replay === replay) stop(); });
}
