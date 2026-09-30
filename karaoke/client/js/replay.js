// "Ouvir minha apresentação": a voz gravada do cantor (recordings/<id>/<nome>.wav,
// já no tempo da música) tocando junto do instrumental, no fim de jogo.
import { state } from './state.js';

const BACKING_VOLUME = 0.55;

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
    const replay = { voice, backing, player, recordingId, button, onStop };
    state.replay = replay;
    if (button) button.classList.add('is-playing');

    // a voz manda no relógio; o instrumental segue
    voice.addEventListener('timeupdate', () => {
        if (Math.abs(backing.currentTime - voice.currentTime) > 0.12) backing.currentTime = voice.currentTime;
    });
    voice.addEventListener('ended', stop);
    voice.addEventListener('error', stop);
    Promise.all([voice.play(), backing.play()]).catch(stop);
}
