// Escrita da letra em músicas japonesas: original (kanji/kana), romaji ou ambos
// (romaji pequeno em cima de cada palavra, como furigana). O servidor manda o
// romaji pronto (`lyrics_romaji` na linha, `romaji` em cada palavra); em outros
// idiomas esses campos não existem e tudo continua como texto normal.
//
// Cada elemento guarda o original e o romaji em data-* para a troca de modo
// redesenhar o que está na tela sem esperar o próximo verso.
import { state } from './state.js';

const STORAGE_KEY = 'karaoke_lyrics_script';
const MODES = ['original', 'romaji', 'both'];

function readSavedMode() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        return MODES.includes(saved) ? saved : 'both';
    } catch {
        return 'both';
    }
}

export function getLyricsScript() {
    if (!state.lyricsScript) state.lyricsScript = readSavedMode();
    return state.lyricsScript;
}

function paintWord(span) {
    const { original, romaji, sep } = span.dataset;
    const mode = getLyricsScript();
    span.replaceChildren();
    if (!romaji || mode === 'original') {
        span.textContent = original + sep;
    } else if (mode === 'romaji') {
        span.textContent = romaji + ' ';
    } else {
        const ruby = document.createElement('ruby');
        ruby.append(original);
        const rt = document.createElement('rt');
        rt.textContent = romaji;
        ruby.append(rt);
        span.append(ruby, sep);
    }
}

function paintLine(el) {
    const { original, romaji } = el.dataset;
    const mode = getLyricsScript();
    el.replaceChildren();
    if (!romaji || mode === 'original') {
        el.textContent = original;
    } else if (mode === 'romaji') {
        el.textContent = romaji;
    } else {
        const sub = document.createElement('span');
        sub.className = 'lyrics-romaji-line';
        sub.textContent = romaji;
        el.append(original, sub);
    }
}

// Palavra da letra (span.word do modo por palavra).
export function fillWord(span, word, romaji, separator) {
    span.dataset.original = word;
    span.dataset.sep = separator;
    if (romaji) span.dataset.romaji = romaji; else delete span.dataset.romaji;
    span.classList.add('lyrics-word');
    paintWord(span);
}

// Linha inteira (verso anterior/próximo, modo por verso, letra no celular).
export function fillLine(el, text, romaji) {
    el.dataset.original = text || '';
    if (romaji) el.dataset.romaji = romaji; else delete el.dataset.romaji;
    el.classList.add('lyrics-line');
    paintLine(el);
}

function repaintAll() {
    document.querySelectorAll('.lyrics-word').forEach(paintWord);
    document.querySelectorAll('.lyrics-line').forEach(paintLine);
}

function syncButtons() {
    const mode = getLyricsScript();
    document.querySelectorAll('.lyrics-script-choice').forEach(btn => {
        btn.setAttribute('aria-pressed', String(btn.dataset.script === mode));
    });
}

export function setLyricsScript(mode) {
    if (!MODES.includes(mode)) return;
    state.lyricsScript = mode;
    try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* sem armazenamento: vale só nesta aba */ }
    syncButtons();
    repaintAll();
}

// Mostra o seletor só quando o verso tem romaji gerado pelo servidor: letra em
// kanji/kana. Letra colada em romaji não tem o que alternar (chamado a cada verso).
export function setLyricsScriptAvailable(romaji) {
    document.querySelectorAll('.lyrics-script-control').forEach(el => { el.hidden = !romaji; });
}

export function initLyricsScriptControls() {
    document.querySelectorAll('.lyrics-script-choice').forEach(btn => {
        btn.addEventListener('click', () => setLyricsScript(btn.dataset.script));
    });
    syncButtons();
}
