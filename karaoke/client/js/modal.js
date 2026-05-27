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

// Pilha de ids de modais abertos (o último é o "topo").
const openStack = [];

// Quantos popstate de fechamento programático devem ser ignorados pelo listener
// global (evita fechar o modal errado quando nós mesmos chamamos history.back()).
let pendingProgrammaticPops = 0;

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
    openStack.push(modal.id);

    // Cada modal aberto vira uma entrada no histórico, para o "voltar" fechá-lo.
    history.pushState({ karaokeModal: modal.id }, '');
    return modal;
}

export function closeModal(idOrEl) {
    const modal = el(idOrEl);
    if (!isOpen(modal)) return;

    applyClose(modal);

    // Desfaz a entrada de histórico que abrimos, sem disparar o fechamento de novo.
    pendingProgrammaticPops++;
    history.back();
}

export function closeTopModal() {
    const topId = openStack[openStack.length - 1];
    if (topId) closeModal(topId);
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
    if (modal) applyClose(modal);
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

function onKeyDown(e) {
    if (e.key !== 'Escape') return;
    const modal = topOpenModal();
    if (modal && !modal.hasAttribute('data-no-esc')) {
        closeModal(modal);
    }
}

window.addEventListener('popstate', onPopState);
document.addEventListener('click', onBackdropClick);
document.addEventListener('keydown', onKeyDown);
