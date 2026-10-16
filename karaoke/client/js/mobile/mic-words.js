// Palavra acesa na letra do celular, como na TV. O servidor manda o tempo da
// música (song_time) no segment_start e no singing_state; entre um e outro o
// celular conta sozinho, na velocidade da TV (remote_state) e parado na pausa.
import { state } from '../core/state.js';

// O singing_state "active" sai 1 s antes do verso (SINGING_PRE_BUFFER_SEC em
// ws/room.py): âncora quando o servidor ainda não manda song_time.
const PRE_SING_SEC = 1.0;

function playbackRate() {
    const s = state.remoteState;
    return s && typeof s.speed === 'number' && s.speed > 0 ? s.speed : 1;
}

function songNow() {
    const a = state.micSongAnchor;
    if (!a) return null;
    const s = state.remoteState;
    if (s && s.paused) return a.t;
    return a.t + ((performance.now() - a.at) / 1000) * playbackRate();
}

function anchor(t) {
    state.micSongAnchor = { t, at: performance.now() };
}

function paint() {
    const verse = state.micVerse;
    const now = songNow();
    if (!verse || now === null) return;
    const rel = now - verse.singStart;
    verse.spans.forEach((span, idx) => {
        const item = verse.timed[idx];
        const next = verse.timed[idx + 1];
        const reached = rel >= item.expected_start;
        const active = reached && now <= verse.singEnd && (!next || rel < next.expected_start);
        span.classList.toggle('active', active);
        span.classList.toggle('passed', reached && !active);
    });
}

function loop() {
    state.micWordsFrame = null;
    if (!state.micVerse) return;
    paint();
    state.micWordsFrame = requestAnimationFrame(loop);
}

// Verso novo na tela: `spans` na ordem de data.lyrics_timed (null = sem acompanhar)
export function followVerse(data, spans) {
    if (typeof data.song_time === 'number') {
        state.micServerClock = true;
        anchor(data.song_time);
    }
    state.micVerse = spans && spans.length
        ? { singStart: data.sing_start, singEnd: data.sing_end, timed: data.lyrics_timed, spans }
        : null;
    if (state.micVerse && !state.micWordsFrame) state.micWordsFrame = requestAnimationFrame(loop);
}

export function stopFollowing() {
    state.micVerse = null;
}

export function onSingingState(data) {
    if (typeof data.song_time === 'number') {
        state.micServerClock = true;
        anchor(data.song_time);
    } else if (data.active && state.micVerse && !state.micServerClock) {
        anchor(state.micVerse.singStart - PRE_SING_SEC);
    }
}
