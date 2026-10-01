// Ouvir um trecho na lista de músicas: ~12 s a partir do refrão (o verso que
// mais se repete na letra) ou, sem repetição, a partir de 1/3 da música.
// Um trecho por vez; abrir uma música ou tocar outro para o atual.
import { state } from '../core/state.js';

const CLIP_SEC = 12;
const FADE_SEC = 1.2;

function normLine(text) {
    return String(text || '').toLowerCase().replace(/[^\p{L}\p{N} ]/gu, '').trim();
}

// Início do refrão: 1ª ocorrência do verso mais repetido (2+ vezes).
export function chorusStart(segments) {
    const counts = {};
    const first = {};
    (segments || []).forEach((seg) => {
        const key = normLine(seg.lyrics);
        if (!key) return;
        counts[key] = (counts[key] || 0) + 1;
        if (first[key] === undefined) first[key] = seg.sing_start;
    });
    let best = null;
    Object.keys(counts).forEach((key) => {
        if (counts[key] >= 2 && (best === null || counts[key] > counts[best])) best = key;
    });
    return best === null ? null : Math.max(0, first[best] - 0.5);
}

export function stopPreview() {
    const p = state.preview;
    if (!p) return;
    clearInterval(p.timer);
    p.audio.pause();
    if (p.button) p.button.classList.remove('is-playing');
    state.preview = null;
}

async function startAt(songId) {
    try {
        const resp = await fetch(`/api/songs/${encodeURIComponent(songId)}`);
        if (resp.ok) {
            const data = await resp.json();
            const t = chorusStart(data.segments);
            if (t !== null) return t;
        }
    } catch (e) { /* sem segmentos: usa o terço da música */ }
    return null;
}

export async function togglePreview(songId, button) {
    const current = state.preview;
    stopPreview();
    if (current && current.songId === songId) return;

    const audio = new Audio(`/songs/${encodeURIComponent(songId)}/audio`);
    audio.volume = 0;
    const preview = { audio, songId, button, timer: null };
    state.preview = preview;
    if (button) button.classList.add('is-playing');

    let start = await startAt(songId);
    if (state.preview !== preview) return;
    audio.addEventListener('loadedmetadata', () => {
        if (start === null) start = (audio.duration || 90) / 3;
        audio.currentTime = start;
        audio.play().catch(stopPreview);
        preview.timer = setInterval(() => {
            const t = audio.currentTime - start;
            if (t >= CLIP_SEC) { stopPreview(); return; }
            // entra e sai suave
            const fadeIn = Math.min(1, t / FADE_SEC);
            const fadeOut = Math.min(1, (CLIP_SEC - t) / FADE_SEC);
            audio.volume = Math.max(0, Math.min(1, Math.min(fadeIn, fadeOut)));
        }, 100);
    }, { once: true });
    audio.addEventListener('error', stopPreview);
}
