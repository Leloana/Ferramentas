// Navegação por controle remoto (D-pad) e teclado — pensada para navegador de TV.
//
// - Setas movem o foco para o elemento focável mais próximo naquela direção
//   (navegação espacial), restrita ao modal/painel aberto por cima.
// - OK/Enter aciona cards e cabeçalhos que não são <button> (role="button").
// - Voltar (Backspace, BrowserBack, Tizen 10009, webOS 461) fecha o que estiver
//   aberto ou recua uma tela; na partida, pausa.
// - Play/Pause do controle inicia ou pausa a música.
// - Ao trocar de tela, o foco vai para a ação principal (ex.: INICIAR).
//
// A classe `using-keys` no <html> liga o contorno de foco (tv.css); some ao usar
// mouse ou toque. `is-tv` (config.isTvBrowser) aumenta a escala da interface.

import { state } from './state.js';
import { isTvBrowser } from './config.js';
import { closeTopModal, hasOpenModal } from './modal.js';
import { closeOpenSelects } from './select.js';

const DIRS = {
    ArrowLeft: 'left', Left: 'left', 37: 'left',
    ArrowUp: 'up', Up: 'up', 38: 'up',
    ArrowRight: 'right', Right: 'right', 39: 'right',
    ArrowDown: 'down', Down: 'down', 40: 'down',
};
const BACK_KEYS = ['BrowserBack', 'GoBack', 'Backspace', 10009, 461];
const PLAY_PAUSE_KEYS = ['MediaPlayPause', 'MediaPlay', 'MediaPause', 10252, 415, 19];

const FOCUSABLE = 'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

const html = document.documentElement;

function keyOf(e) {
    return e.key && e.key !== 'Unidentified' ? e.key : e.keyCode;
}

function isVisible(el) {
    if (el.disabled) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    return getComputedStyle(el).visibility !== 'hidden';
}

function isTextField(el) {
    if (!el) return false;
    if (el.tagName === 'TEXTAREA') return true;
    if (el.tagName !== 'INPUT') return false;
    return ['text', 'search', 'url', 'email', 'number', 'password', 'tel'].indexOf(el.type || 'text') !== -1;
}

// Camada de cima: modal aberto (maior z-index) ou a página.
function activeScope() {
    const overlays = Array.prototype.slice.call(document.querySelectorAll('.modal-overlay[data-open]'));
    if (overlays.length) {
        overlays.sort((a, b) => (parseInt(getComputedStyle(a).zIndex, 10) || 0) - (parseInt(getComputedStyle(b).zIndex, 10) || 0));
        return overlays[overlays.length - 1];
    }
    return document.body;
}

function focusables(scope) {
    return Array.prototype.slice.call(scope.querySelectorAll(FOCUSABLE)).filter(isVisible);
}

function focusEl(el) {
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

// Distância na direção pedida: gap no eixo principal + 2× desalinhamento no eixo
// cruzado (0 quando as projeções se sobrepõem). Candidatos para trás são ignorados.
function score(from, to, dir) {
    const fc = { x: from.left + from.width / 2, y: from.top + from.height / 2 };
    const tc = { x: to.left + to.width / 2, y: to.top + to.height / 2 };
    let primary;
    let cross;
    if (dir === 'left' || dir === 'right') {
        if (dir === 'right' ? tc.x <= fc.x + 1 : tc.x >= fc.x - 1) return Infinity;
        primary = dir === 'right' ? to.left - from.right : from.left - to.right;
        cross = Math.max(0, Math.max(from.top, to.top) - Math.min(from.bottom, to.bottom));
    } else {
        if (dir === 'down' ? tc.y <= fc.y + 1 : tc.y >= fc.y - 1) return Infinity;
        primary = dir === 'down' ? to.top - from.bottom : from.top - to.bottom;
        cross = Math.max(0, Math.max(from.left, to.left) - Math.min(from.right, to.right));
    }
    return Math.max(0, primary) + cross * 2 + Math.hypot(tc.x - fc.x, tc.y - fc.y) * 0.01;
}

function move(dir) {
    const scope = activeScope();
    const items = focusables(scope);
    if (!items.length) return false;

    const current = document.activeElement;
    if (!current || current === document.body || !scope.contains(current) || !isVisible(current)) {
        focusEl(preferredTarget(scope, items));
        return true;
    }

    const from = current.getBoundingClientRect();
    let best = null;
    let bestScore = Infinity;
    items.forEach((el) => {
        if (el === current) return;
        const s = score(from, el.getBoundingClientRect(), dir);
        if (s < bestScore) { bestScore = s; best = el; }
    });
    if (best) focusEl(best);
    return !!best;
}

// Onde o foco cai quando ainda não há foco (ou a tela mudou).
function preferredTarget(scope, items) {
    const pick = (sel) => {
        const el = scope.querySelector(sel);
        return el && isVisible(el) ? el : null;
    };
    if (scope === document.body) {
        const s = state.currentAppState;
        if (s === 'waiting') return pick('#btn-start') || items[0];
        if (s === 'singing') return pick('#btn-pause-play') || items[0];
        return (state.lastFocusedSong && document.body.contains(state.lastFocusedSong) && isVisible(state.lastFocusedSong) && state.lastFocusedSong)
            || pick('.tab-btn[aria-selected="true"]') || items[0];
    }
    return pick('[data-autofocus]') || items.filter((el) => !isTextField(el))[0] || items[0];
}

function clickById(id) {
    const el = document.getElementById(id);
    if (el && isVisible(el)) { el.click(); return true; }
    return false;
}

function goBack() {
    if (closeOpenSelects()) return true; // lista de um select aberta: fecha só ela
    if (hasOpenModal()) { closeTopModal(); return true; }

    // Fim de jogo não passa pelo modal.js (abre direto por atributo)
    const gameOver = document.getElementById('game-over-modal');
    if (gameOver && gameOver.hasAttribute('data-open')) return clickById('btn-restart-game');

    switch (state.currentAppState) {
        case 'waiting': return clickById('btn-back');
        case 'singing': return clickById('btn-pause-play');
        case 'idle': {
            const queueTab = document.getElementById('tab-btn-queue');
            if (queueTab && queueTab.getAttribute('aria-selected') === 'true') return clickById('tab-btn-songs');
            return false; // deixa a TV tratar (sair do navegador)
        }
        default: return false;
    }
}

function playPause() {
    if (state.currentAppState === 'waiting') return clickById('btn-start');
    if (state.currentAppState === 'singing') return clickById('btn-pause-play');
    return false;
}

function onKeyDown(e) {
    const key = keyOf(e);
    const target = e.target;
    const dir = DIRS[key];

    if (dir) {
        html.classList.add('using-keys');
        // Campos de texto: setas laterais movem o cursor até a borda do texto.
        if (isTextField(target)) {
            const atStart = target.selectionStart === 0 && target.selectionEnd === 0;
            const atEnd = target.selectionStart === target.value.length;
            if (dir === 'left' && !atStart) return;
            if (dir === 'right' && !atEnd) return;
            if (target.tagName === 'TEXTAREA' && ((dir === 'up' && !atStart) || (dir === 'down' && !atEnd))) return;
        }
        // Slider: esquerda/direita ajustam o valor.
        if (target && target.type === 'range' && (dir === 'left' || dir === 'right')) return;
        if (move(dir)) e.preventDefault();
        return;
    }

    if (key === 'Enter' || key === 13 || key === ' ' || key === 32) {
        // <button>, <a> e campos já tratam OK/Enter sozinhos; cards e cabeçalhos
        // (role="button" com tabindex) precisam do clique sintético.
        const native = target && target.matches && target.matches('button, a, input, select, textarea');
        if (!native && target && target.matches && target.matches('[role="button"], [tabindex]')) {
            e.preventDefault();
            target.click();
        }
        return;
    }

    if (PLAY_PAUSE_KEYS.indexOf(key) !== -1) {
        if (playPause()) e.preventDefault();
        return;
    }

    // Esc com modal aberto fica com o modal.js; sem modal, vale como "voltar".
    if (key === 'Escape' && hasOpenModal()) return;
    if (key === 'Escape' || BACK_KEYS.indexOf(key) !== -1 || e.keyCode === 10009 || e.keyCode === 461) {
        if (key === 'Backspace' && isTextField(target)) return;
        if (goBack()) e.preventDefault();
    }
}

// Ao trocar de tela ou abrir um modal, leva o foco para a ação principal.
function watchScreens() {
    const app = document.getElementById('app');
    const refocus = () => {
        if (!html.classList.contains('using-keys') && !isTvBrowser) return;
        // espera o CSS aplicar o novo estado antes de medir visibilidade
        requestAnimationFrame(() => {
            const scope = activeScope();
            const items = focusables(scope);
            if (items.length && (!scope.contains(document.activeElement) || !isVisible(document.activeElement))) {
                focusEl(preferredTarget(scope, items));
            }
        });
    };
    if (!window.MutationObserver) return;
    const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
            if (m.attributeName === 'data-state' || m.attributeName === 'data-open') { refocus(); return; }
        }
    });
    if (app) observer.observe(app, { attributes: true, attributeFilter: ['data-state'] });
    document.querySelectorAll('.modal-overlay').forEach((el) => {
        observer.observe(el, { attributes: true, attributeFilter: ['data-open'] });
    });
}

export function initTvNav() {
    if (isTvBrowser) html.classList.add('is-tv', 'using-keys');

    // captura: roda antes do Esc do modal.js, para não fechar e voltar no mesmo toque
    document.addEventListener('keydown', onKeyDown, true);
    const dropKeys = () => { if (!isTvBrowser) html.classList.remove('using-keys'); };
    document.addEventListener('mousedown', dropKeys, true);
    document.addEventListener('touchstart', dropKeys, { capture: true, passive: true });

    // Lembra a última música focada para voltar nela ao sair da partida.
    document.addEventListener('focusin', (e) => {
        if (e.target && e.target.classList && e.target.classList.contains('song-card')) {
            state.lastFocusedSong = e.target;
        }
    });

    watchScreens();
}
