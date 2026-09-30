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

function stop() {
    const r = state.replay;
    if (!r) return;
    r.voice.pause();
    r.backing.pause();
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
    voice.addEventListener('ended', stop);
    voice.addEventListener('error', stop);

    // só começa com os dois prontos para tocar, juntos do zero
    Promise.all([ready(voice), ready(backing)]).then(() => {
        if (state.replay !== replay) return;
        return Promise.all([voice.play(), backing.play()]);
    }).catch(() => { if (state.replay === replay) stop(); });
}
