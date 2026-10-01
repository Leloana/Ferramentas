// Faixa "Ouvi:" da TV: o que o Whisper entendeu no último verso, com acerto e
// erro por palavra, e o aviso de espera entre um verso e outro.
import { state } from '../core/state.js';

const HEARD_HOLD_MS = 3500;

function transcriptionEl() {
    return document.getElementById('transcription-text');
}

// Compara palavras sem acento e pontuação ("não" == "nao"). O \w do JS só
// cobre ASCII: com ele "não" virava "no" e o acerto aparecia como erro.
function normalizeWord(word) {
    return String(word).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
}

export function expectedWords(lyricsTimed) {
    return lyricsTimed ? lyricsTimed.map(w => normalizeWord(w.word)) : [];
}

function setHint(el, text, showHeader) {
    el.innerHTML = `${showHeader ? '<strong>Ouvi:</strong> ' : ''}<span class="muted">${text}</span>`;
}

// hits (opcional, do servidor): acerto de cada palavra ouvida, na mesma ordem. Sem ele,
// compara com a letra aqui (não serve para japonês, que o servidor casa em romaji).
export function renderTranscriptionInto(container, transcription, expectedNormalized, showHeader = true, hits = null) {
    if (!container) return;
    container.innerHTML = '';

    if (!transcription || !transcription.trim()) {
        setHint(container, '[Silêncio]', showHeader);
        return;
    }

    if (showHeader) {
        container.innerHTML = '<strong>Ouvi:</strong> ';
    }
    const words = transcription.trim().split(/\s+/);
    const useHits = Array.isArray(hits) && hits.length === words.length;
    words.forEach((word, i) => {
        const isMatch = useHits ? hits[i] : expectedNormalized.includes(normalizeWord(word));
        const span = document.createElement('span');
        span.innerText = word + ' ';
        span.className = isMatch ? 'heard-word heard-word--hit' : 'heard-word heard-word--miss';
        container.appendChild(span);
    });
}

// Aviso de espera ("[Ouvindo...]", "[Solo Instrumental...]"...). Por padrão não
// apaga uma transcrição que ainda está na tela.
export function showHeardHint(text, force = false) {
    const el = transcriptionEl();
    if (!el || (!force && state.transcriptionActiveTimer)) return;
    setHint(el, text, true);
}

export function listeningHint() {
    return state.isSingingActive ? '[Ouvindo...]' : '[Solo Instrumental...]';
}

// Resultado de um verso: fica na tela por HEARD_HOLD_MS e volta ao aviso de espera.
export function showHeardResult(transcription, expectedNormalized, hits = null) {
    const el = transcriptionEl();
    if (!el) return;
    if (transcription && transcription.trim()) {
        renderTranscriptionInto(el, transcription, expectedNormalized, true, hits);
    } else {
        setHint(el, '[Silêncio ou Incompreensível]', true);
    }
    clearHeardTimer();
    state.transcriptionActiveTimer = setTimeout(() => {
        state.transcriptionActiveTimer = null;
        if (state.currentAppState !== 'idle') showHeardHint(listeningHint(), true);
    }, HEARD_HOLD_MS);
}

export function clearHeardTimer() {
    if (state.transcriptionActiveTimer) {
        clearTimeout(state.transcriptionActiveTimer);
        state.transcriptionActiveTimer = null;
    }
}
