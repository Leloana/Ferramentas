// Gerenciador único de modais.
//
// Centraliza abrir/fechar, fechar ao clicar fora (backdrop), fechar com ESC e
// integração com o histórico do navegador (o botão "voltar" fecha o modal aberto).
//
// Antes, cada modal era aberto/fechado manualmente com `setAttribute('data-open')`
// espalhado pelos módulos, sem padrão de fechamento. Agora todos passam por aqui.
//
// Uso:
//   import { openModal, closeModal } from './modal.js';
//   openModal('add-song-modal');
//   openModal('generation-options-modal', { onClose: () => resolve(null) });
//   closeModal('add-song-modal');
//
// Markup opcional no `.modal-overlay`:
//   data-no-backdrop  -> não fecha ao clicar fora
//   data-no-esc       -> não fecha com a tecla ESC
//   [data-close]      -> qualquer elemento interno com este atributo fecha o modal ao clicar
//
// `modal._onBack = () => bool`: "voltar" (Esc, botão do navegador, Voltar da
// TV) chama antes de fechar; devolvendo true o modal só recua um passo.

// Pilha de ids de modais abertos (o último é o "topo").
const openStack = [];

// Quantos popstate de fechamento programático devem ser ignorados pelo listener
// global (evita fechar o modal errado quando nós mesmos chamamos history.back()).
let pendingProgrammaticPops = 0;

// Entradas de histórico de modais já fechados que ainda vamos desfazer. O
// history.back() é adiado um tick: se outro modal abrir nesse meio-tempo
// (fechar um e abrir outro, ex.: picker → pareamento) ele reaproveita a
// entrada. Antes o back atrasado apagava a entrada do modal novo, e o
// "Fechar" dele saía do app.
let entriesToUndo = 0;
let undoTimer = null;

function flushUndo() {
    undoTimer = null;
    if (entriesToUndo <= 0) return;
    const n = entriesToUndo;
    entriesToUndo = 0;
    pendingProgrammaticPops++;  // history.go(-n) dispara um único popstate
    history.go(-n);
}

function el(idOrEl) {
    return typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
}

function isOpen(modal) {
    return !!modal && modal.hasAttribute('data-open');
}

function detach(modal) {
    const idx = openStack.lastIndexOf(modal.id);
    if (idx !== -1) openStack.splice(idx, 1);
}

// Remove o estado visual e dispara o callback de fechamento, sem mexer no histórico.
function applyClose(modal) {
    if (!isOpen(modal)) return;
    modal.removeAttribute('data-open');
    detach(modal);
    const cb = modal._onClose;
    modal._onClose = null;
    if (typeof cb === 'function') cb();
}

export function openModal(idOrEl, options = {}) {
    const modal = el(idOrEl);
    if (!modal || isOpen(modal)) return modal;

    modal.setAttribute('data-open', 'true');
    modal._onClose = options.onClose || null;
    // modal sempre abre rolado no início
    const scroller = modal.querySelector('.modal-content, .paper-card');
    if (scroller) scroller.scrollTop = 0;
    openStack.push(modal.id);

    // Cada modal aberto vira uma entrada no histórico, para o "voltar" fechá-lo.
    if (entriesToUndo > 0) {
        entriesToUndo--;
        history.replaceState({ karaokeModal: modal.id }, '');
    } else {
        history.pushState({ karaokeModal: modal.id }, '');
    }
    return modal;
}

export function closeModal(idOrEl) {
    const modal = el(idOrEl);
    if (!isOpen(modal)) return;

    applyClose(modal);

    // Desfaz a entrada de histórico que abrimos, sem disparar o fechamento de novo.
    entriesToUndo++;
    if (!undoTimer) undoTimer = setTimeout(flushUndo, 0);
}

export function hasOpenModal() {
    return openStack.length > 0;
}

function stepBack(modal) {
    return !!(modal && typeof modal._onBack === 'function' && modal._onBack());
}

// "Voltar" genérico (tv-nav.js): recua um passo se o modal souber, senão fecha.
export function closeTopModal() {
    const topId = openStack[openStack.length - 1];
    if (!topId) return;
    if (stepBack(el(topId))) return;
    closeModal(topId);
}

// --- Listeners globais (instalados uma única vez) ---

function topOpenModal() {
    return el(openStack[openStack.length - 1]);
}

function onPopState() {
    if (pendingProgrammaticPops > 0) {
        pendingProgrammaticPops--;
        return;
    }
    // Botão "voltar" do navegador: fecha o modal do topo, se houver.
    const modal = topOpenModal();
    if (!modal) return;
    if (stepBack(modal)) {
        // recuou um passo: o modal segue aberto, então devolve a entrada
        history.pushState({ karaokeModal: modal.id }, '');
        return;
    }
    applyClose(modal);
}

function onBackdropClick(e) {
    const modal = topOpenModal();
    if (!modal) return;
    // Só fecha se o clique foi no próprio overlay (fundo), não no conteúdo.
    if (e.target === modal && !modal.hasAttribute('data-no-backdrop')) {
        closeModal(modal);
        return;
    }
    // Botões/elementos marcados com [data-close] fecham o modal que os contém.
    const closer = e.target.closest('[data-close]');
    if (closer && modal.contains(closer)) {
        closeModal(modal);
    }
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Tab com modal aberto circula só dentro dele (senão o foco ia para trás do fundo).
function trapTab(e, modal) {
    const items = Array.prototype.filter.call(modal.querySelectorAll(FOCUSABLE),
        (node) => node.offsetWidth > 0 || node.offsetHeight > 0);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const inside = modal.contains(document.activeElement);
    if (e.shiftKey && (document.activeElement === first || !inside)) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && (document.activeElement === last || !inside)) {
        e.preventDefault();
        first.focus();
    }
}

function onKeyDown(e) {
    if (e.key === 'Tab') {
        // o fim de jogo abre por atributo, fora da pilha: também prende o Tab
        const trapIn = topOpenModal() || document.querySelector('.modal-overlay[data-open]');
        if (trapIn) trapTab(e, trapIn);
        return;
    }
    const modal = topOpenModal();
    if (!modal) return;
    if (e.key !== 'Escape') return;
    if (modal.hasAttribute('data-no-esc')) return;
    if (stepBack(modal)) return;
    closeModal(modal);
}

window.addEventListener('popstate', onPopState);
document.addEventListener('click', onBackdropClick);
document.addEventListener('keydown', onKeyDown);
