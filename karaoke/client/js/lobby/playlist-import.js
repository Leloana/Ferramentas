// Playlist do YouTube no "Adicionar música": lista as músicas, deixa marcar e
// corrigir artista/título de cada uma e enfileira as marcadas de uma vez.
//
// O tempo estimado vem de POST /api/queue/estimate (fila atual + as marcadas),
// recalculado a cada mudança na seleção.

import { state } from '../core/state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from '../core/dom.js';
import { showToast } from '../core/toast.js';
import { formatEta } from './queue-view.js';

const PLAYLIST_RE = /(youtube\.com|youtu\.be)\/.*[?&]list=[\w-]+/i;
const ESTIMATE_DELAY_MS = 350;

export function isPlaylistUrl(text) {
    return PLAYLIST_RE.test(text || '');
}

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

function formatDuration(sec) {
    if (!sec && sec !== 0) return '';
    const s = Math.round(sec);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const STATUS_LABEL = { library: 'Já na biblioteca', queue: 'Já na fila' };

function selectedItems() {
    const pl = state.playlistImport;
    return pl ? pl.items.filter((item) => item.checked) : [];
}

function updateSubmitLabel() {
    const btn = document.getElementById('btn-submit-song');
    if (!btn) return;
    const n = selectedItems().length;
    btn.innerText = n ? `Adicionar ${n} à fila` : 'Adicionar à fila';
    btn.disabled = n === 0;
}

function renderSummary(etaText) {
    const pl = state.playlistImport;
    const summary = document.getElementById('playlist-summary');
    const toggle = document.getElementById('btn-playlist-toggle-all');
    if (!pl || !summary) return;
    const n = selectedItems().length;
    const parts = [`${n} de ${pl.items.length} marcadas`];
    if (n && etaText) parts.push(etaText);
    summary.textContent = parts.join(' · ');
    if (toggle) toggle.textContent = n === pl.items.length ? 'Desmarcar todas' : 'Marcar todas';
}

// Tempo até tudo ficar pronto, contando o que já está na fila.
async function refreshEstimate() {
    const pl = state.playlistImport;
    if (!pl) return;
    const picked = selectedItems();
    const ticket = ++pl.estimateTicket;
    if (!picked.length) {
        renderSummary('');
        return;
    }
    renderSummary('calculando tempo...');
    try {
        const resp = await fetch('/api/queue/estimate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ durations: picked.map((item) => item.duration || null) }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'falha');
        if (ticket !== pl.estimateTicket) return; // seleção mudou no meio
        const eta = formatEta(data.total_sec);
        renderSummary(eta ? `prontas em ${eta}${data.queued ? ' (com a fila atual)' : ''}` : '');
    } catch (err) {
        if (ticket === pl.estimateTicket) renderSummary('');
    }
}

function scheduleEstimate() {
    const pl = state.playlistImport;
    if (!pl) return;
    updateSubmitLabel();
    renderSummary('');
    clearTimeout(pl.estimateTimer);
    pl.estimateTimer = setTimeout(refreshEstimate, ESTIMATE_DELAY_MS);
}

function renderItem(item) {
    const row = el('div', 'playlist-item');
    const check = el('input', 'playlist-item__check');
    check.type = 'checkbox';
    check.checked = item.checked;
    check.setAttribute('aria-label', item.title);

    const thumb = el('img', 'playlist-item__thumb');
    thumb.src = item.thumbnail;
    thumb.alt = '';
    thumb.loading = 'lazy';

    const fields = el('div', 'playlist-item__fields');
    const titleInput = el('input', 'input playlist-item__title-input');
    titleInput.type = 'text';
    titleInput.value = item.title_guess || '';
    titleInput.placeholder = 'Título';
    titleInput.setAttribute('aria-label', 'Título');
    const artistInput = el('input', 'input');
    artistInput.type = 'text';
    artistInput.value = item.artist_guess || '';
    artistInput.placeholder = 'Artista';
    artistInput.setAttribute('aria-label', 'Artista');

    const meta = el('div', 'playlist-item__meta');
    const duration = formatDuration(item.duration);
    if (duration) meta.append(el('span', '', duration));
    if (STATUS_LABEL[item.status]) {
        const chip = el('span', 'chip', STATUS_LABEL[item.status]);
        chip.dataset.tone = item.status === 'library' ? 'sage' : 'blue';
        meta.append(chip);
    }
    meta.append(el('span', 'playlist-item__orig', item.title));
    fields.append(titleInput, artistInput, meta);
    row.append(check, thumb, fields);

    const paint = () => row.classList.toggle('is-off', !item.checked);
    paint();
    check.addEventListener('change', () => {
        item.checked = check.checked;
        paint();
        scheduleEstimate();
    });
    titleInput.addEventListener('input', () => { item.title_guess = titleInput.value; });
    artistInput.addEventListener('input', () => { item.artist_guess = artistInput.value; });
    item.row = row;
    item.check = check;
    item.titleInput = titleInput;
    item.artistInput = artistInput;
    return row;
}

function renderList() {
    const pl = state.playlistImport;
    const list = document.getElementById('playlist-items');
    const title = document.getElementById('playlist-title');
    if (!pl || !list) return;
    if (title) title.textContent = pl.title || 'Playlist';
    list.replaceChildren(...pl.items.map(renderItem));
    if (pl.truncated) list.append(el('p', 'yt-results__msg', `Só as primeiras ${pl.items.length} músicas da playlist.`));
    scheduleEstimate();
}

// Busca a playlist e mostra o passo "playlist". true se deu certo.
export async function openPlaylist(url) {
    const results = document.getElementById('youtube-results');
    const btn = document.getElementById('btn-youtube-search');
    if (btn) btn.disabled = true;
    if (results) results.replaceChildren(el('p', 'yt-results__msg', 'Lendo a playlist...'));
    try {
        const resp = await fetch(`/api/youtube-playlist?url=${encodeURIComponent(url)}`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Falha ao ler a playlist');
        const items = (data.results || []).map((item) => Object.assign({}, item, {
            checked: item.status === 'new',
        }));
        if (!items.length) throw new Error('Nenhuma música disponível nessa playlist.');
        state.playlistImport = {
            title: data.title, items, truncated: data.truncated, estimateTicket: 0, estimateTimer: null,
        };
        if (results) results.replaceChildren();
        renderList();
        return true;
    } catch (err) {
        if (results) results.replaceChildren(el('p', 'yt-results__msg', err.message));
        return false;
    } finally {
        if (btn) btn.disabled = false;
    }
}

export function closePlaylist() {
    const pl = state.playlistImport;
    if (pl) clearTimeout(pl.estimateTimer);
    state.playlistImport = null;
    const list = document.getElementById('playlist-items');
    if (list) list.replaceChildren();
    const btn = document.getElementById('btn-submit-song');
    if (btn) btn.disabled = false;
}

export function initPlaylistImport() {
    const toggle = document.getElementById('btn-playlist-toggle-all');
    if (!toggle) return;
    toggle.addEventListener('click', () => {
        const pl = state.playlistImport;
        if (!pl) return;
        const all = selectedItems().length === pl.items.length;
        pl.items.forEach((item) => {
            item.checked = !all;
            item.check.checked = !all;
            item.row.classList.toggle('is-off', all);
        });
        scheduleEstimate();
    });
}

// Enfileira as marcadas, uma por vez (cada uma busca a própria letra no servidor).
// Devolve true quando terminou (mesmo com algumas falhas).
export async function submitPlaylist() {
    const picked = selectedItems();
    if (!picked.length) return false;
    const missing = picked.find((item) => !item.titleInput.value.trim() || !item.artistInput.value.trim());
    if (missing) {
        showToast('Preencha título e artista das músicas marcadas.', 'error');
        (missing.titleInput.value.trim() ? missing.artistInput : missing.titleInput).focus();
        return false;
    }

    const language = document.getElementById('song-language').value;
    const gen = startLoadingOverlay('Adicionando a playlist...', `0 de ${picked.length}`);
    let added = 0;
    const failed = [];
    let lastEta = null;
    for (let i = 0; i < picked.length; i++) {
        const item = picked[i];
        dom.loadingStatusDesc.innerText = `${i + 1} de ${picked.length} · ${item.titleInput.value.trim()}`;
        const form = new FormData();
        form.set('title', item.titleInput.value.trim());
        form.set('artist', item.artistInput.value.trim());
        form.set('language', language);
        form.set('youtube_url', item.url);
        if (item.duration) form.set('duration_sec', item.duration);
        try {
            const resp = await fetch('/api/queue/add', { method: 'POST', body: form });
            const data = await resp.json();
            if (!resp.ok) {
                failed.push(item.titleInput.value.trim());
                if (resp.status === 429) {
                    // fila cheia: as próximas também falhariam
                    picked.slice(i + 1).forEach((rest) => failed.push(rest.titleInput.value.trim()));
                    break;
                }
                continue;
            }
            added++;
            if (data.item && data.item.eta_sec !== undefined) lastEta = data.item.eta_sec;
        } catch (err) {
            failed.push(item.titleInput.value.trim());
        }
    }
    stopLoadingOverlay(gen);

    if (added) {
        const eta = formatEta(lastEta);
        showToast(`${added} música${added > 1 ? 's' : ''} na fila${eta ? ` · prontas em ${eta}` : ''}.`, 'success');
    }
    if (failed.length) {
        showToast(`Não entraram na fila: ${failed.slice(0, 3).join(', ')}${failed.length > 3 ? ` e mais ${failed.length - 3}` : ''}.`, 'error');
    }
    return added > 0;
}
