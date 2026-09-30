// Trocar a capa do álbum: grade com as opções achadas pelo servidor (iTunes,
// Deezer, YouTube), a melhor primeiro. Escolher baixa a capa e atualiza o lobby.
import { state } from './state.js';
import { openModal, closeModal } from './modal.js';
import { showToast } from './toast.js';
import { iconSvg } from './icons.js';

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

// Recarrega a capa do lobby (e das telas que a usam) sem o cache antigo.
export function refreshCover(songId) {
    const img = document.getElementById('current-song-cover');
    if (!img || state.selectedSongId !== songId) return;
    img.onload = () => { img.hidden = false; };
    img.src = `/api/songs/${encodeURIComponent(songId)}/cover?v=${Date.now()}`;
}

async function choose(songId, url, button) {
    button.disabled = true;
    try {
        const resp = await fetch(`/api/songs/${encodeURIComponent(songId)}/cover`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        if (!resp.ok) throw new Error('Não foi possível usar esta capa');
        refreshCover(songId);
        closeModal('cover-picker-modal');
    } catch (e) {
        showToast(e.message, 'error');
        button.disabled = false;
    }
}

async function openPicker() {
    const songId = state.selectedSongId;
    const grid = document.getElementById('cover-picker-grid');
    if (!songId || !grid) return;
    grid.replaceChildren(el('p', 'profile-empty', 'Buscando capas...'));
    openModal('cover-picker-modal');
    let data;
    try {
        const resp = await fetch(`/api/songs/${encodeURIComponent(songId)}/cover/options`);
        if (!resp.ok) throw new Error('Falha ao buscar capas');
        data = await resp.json();
    } catch (e) {
        grid.replaceChildren(el('p', 'profile-empty', 'Sem conexão para buscar capas'));
        return;
    }
    grid.replaceChildren();
    if (!data.options.length) {
        grid.append(el('p', 'profile-empty', 'Nenhuma capa encontrada'));
        return;
    }
    data.options.forEach((opt) => {
        const btn = el('button', 'cover-option');
        btn.type = 'button';
        if (opt.url === data.current) btn.setAttribute('aria-current', 'true');
        const img = el('img', 'cover-option__img');
        img.src = opt.thumb || opt.url;
        img.alt = '';
        img.loading = 'lazy';
        img.onerror = () => btn.remove();
        btn.append(img, el('span', 'cover-option__album', opt.album || opt.source), el('span', 'cover-option__source', opt.source));
        if (opt.url === data.current) btn.insertAdjacentHTML('beforeend', iconSvg('check', 'cover-option__check'));
        btn.addEventListener('click', () => choose(songId, opt.url, btn));
        grid.append(btn);
    });
    const first = grid.querySelector('.cover-option');
    if (first && document.documentElement.classList.contains('using-keys')) first.focus();
}

export function initCoverPicker() {
    const btn = document.getElementById('btn-change-cover');
    if (btn) btn.addEventListener('click', openPicker);
    const img = document.getElementById('current-song-cover');
    if (img) img.addEventListener('click', openPicker);
}
