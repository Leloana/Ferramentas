// Verso comprido no palco (rap, letra gerada sem LRC): o verso atual encolhe e, se
// ainda passar de VISIBLE_ROWS linhas, vira uma janela que rola acompanhando a palavra
// cantada (no modo verso, o tempo do verso). TV rola seco, sem animação (tv.css).
// Antes a linha tinha altura fixa: no PC cortava o verso, na TV estourava o palco.
import { isTvBrowser } from '../core/config.js';

const SHRINK_FROM_ROWS = 3;   // a partir disso a fonte diminui (is-long)
const SCROLL_FROM_ROWS = 4;   // ainda assim grande: janela que rola (is-scroll)

function lineHeightPx(el) {
    const cs = getComputedStyle(el);
    const lh = parseFloat(cs.lineHeight);
    return isNaN(lh) ? parseFloat(cs.fontSize) * 1.25 : lh;
}

// Linhas de texto que o verso ocupa: pelas palavras (topos distintos) ou pela altura.
function countRows(el) {
    const words = el.querySelectorAll('.word');
    if (words.length) {
        const tops = [];
        words.forEach((w) => {
            const t = Math.round(w.offsetTop);
            if (!tops.some(x => Math.abs(x - t) < 4)) tops.push(t);
        });
        return tops.length;
    }
    return Math.round(el.scrollHeight / lineHeightPx(el));
}

// Chamado sempre que o verso atual é redesenhado.
export function fitLongVerse(el) {
    if (!el) return;
    el.classList.remove('is-long', 'is-scroll');
    el.scrollTop = 0;
    el.dataset.followTop = '0';
    if (countRows(el) < SHRINK_FROM_ROWS) return;
    el.classList.add('is-long');
    if (countRows(el) >= SCROLL_FROM_ROWS) el.classList.add('is-scroll');
}

function scrollLine(el, top) {
    const target = Math.max(0, Math.round(top));
    if (el.dataset.followTop === String(target)) return;  // nada a fazer neste quadro
    el.dataset.followTop = String(target);
    if (isTvBrowser || !el.scrollTo) el.scrollTop = target;
    else el.scrollTo({ top: target, behavior: 'smooth' });
}

// Modo palavra: a linha da palavra ativa fica na 2ª linha da janela (uma de contexto acima).
export function followWord(el, wordEl) {
    if (!el || !wordEl || !el.classList.contains('is-scroll')) return;
    scrollLine(el, wordEl.offsetTop - lineHeightPx(el));
}

// Modo verso: rola na proporção do tempo cantado.
export function followProgress(el, fraction) {
    if (!el || !el.classList.contains('is-scroll')) return;
    const max = el.scrollHeight - el.clientHeight;
    const f = Math.max(0, Math.min(1, fraction));
    // degraus de uma linha: rolar pixel a pixel redesenharia a TV a cada quadro
    const step = lineHeightPx(el);
    scrollLine(el, Math.floor((f * max) / step) * step);
}
