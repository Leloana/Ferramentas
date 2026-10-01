/**
 * queue-view.js — Módulo de Fila de Músicas
 *
 * Mostra a fila de processamento (aba "Adicionar") e faz o polling de status.
 * Adicionar música é sempre pelo fluxo padrão (add-song-modal.js).
 * Funciona tanto no modo 'display' (TV) quanto no modo 'mic' (celular).
 */
import { showToast } from '../core/toast.js';
import { iconSvg } from '../core/icons.js';
import { fetchSongs } from './selection-view.js';
import { escapeHtml } from '../core/html.js';
import { state } from '../core/state.js';

// ── Status labels e ícones para cada estado da fila ──
const STATUS_MAP = {
    queued:              { icon: 'hourglass', label: 'Na fila...' },
    downloading:         { icon: 'download', label: 'Baixando do YouTube...' },
    separating:          { icon: 'split', label: 'Separando vocal (Demucs GPU)...' },
    awaiting_alignment:  { icon: 'pause', label: 'Aguardando GPU livre para alinhar...' },
    aligning:            { icon: 'target', label: 'Alinhando letra (Whisper + MMS)...' },
    finalizing:          { icon: 'seal', label: 'Finalizando segmentos...' },
    ready:               { icon: 'check', label: 'Pronta para cantar!' },
    error:               { icon: 'cross', label: 'Erro no processamento' },
    searching:           { icon: 'search', label: 'Buscando letra...' },
    'lyrics-error':      { icon: 'cross', label: 'Letra não encontrada' },
};

let pollInterval = null;

// Listas da fila: aba "Adicionar" da TV e aba "Adicionar" do celular-microfone.
const LIST_IDS = ['queue-display-list', 'queue-mic-list'];

// ── Inicialização ──
export function initQueueView() {
    const displayResetBtn = document.getElementById('queue-display-gpu-reset');
    if (displayResetBtn) {
        displayResetBtn.addEventListener('click', () => clearGpuLock());
    }

    // Polling de status (a cada 3s)
    startPolling();
}

async function clearGpuLock() {
    try {
        const resp = await fetch('/api/queue/clear_gpu_lock', { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Erro ao liberar GPU.');
        }
        showToast('GPU redefinida para livre com sucesso!', 'success');
        await pollQueueStatus();
    } catch (err) {
        showToast('Erro ao liberar GPU: ' + err.message, 'error');
    }
}

// ── Polling de status ──
function startPolling() {
    // Poll imediatamente
    pollQueueStatus();
    // Depois a cada 3 segundos
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollQueueStatus, 3000);
}

export function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

let _previousReadyCount = 0;

// Mutex de GPU: enquanto uma música gera a letra, o INICIAR fica bloqueado
// com o motivo e volta sozinho quando termina (o servidor também recusa).
export function applyStartBlock(busyLabel) {
    state.gpuBlock = busyLabel;
    const btn = document.getElementById('btn-start');
    const note = document.getElementById('start-block-note');
    if (!btn) return;
    if (busyLabel) {
        btn.disabled = true;
        btn.dataset.blocked = 'true';
        btn.innerText = 'GPU OCUPADA';
        if (note) { note.textContent = `Gerando a letra de ${busyLabel}`; note.hidden = false; }
    } else if (btn.dataset.blocked) {
        delete btn.dataset.blocked;
        btn.disabled = false;
        btn.innerText = 'INICIAR';
        if (note) note.hidden = true;
    }
}

async function pollQueueStatus() {
    try {
        const resp = await fetch('/api/queue/status');
        if (!resp.ok) return;
        const data = await resp.json();

        const items = data.queue || [];
        const gpuBusy = data.gpu_busy || false;
        applyStartBlock(data.alignment_busy || null);

        LIST_IDS.forEach((id) => renderQueueItems(id, items));

        // Atualiza badges de contagem
        updateBadges(items);

        // Atualiza indicadores de GPU
        updateGpuBadge('queue-display-gpu-badge', 'queue-display-gpu-text', gpuBusy);
        const displayResetBtn = document.getElementById('queue-display-gpu-reset');
        if (displayResetBtn) displayResetBtn.hidden = !gpuBusy;

        // Notifica quando música ficou pronta
        const readyCount = items.filter(i => i.status === 'ready').length;
        if (readyCount > _previousReadyCount && _previousReadyCount >= 0) {
            const newReady = items.filter(i => i.status === 'ready').slice(-1)[0];
            if (newReady) {
                showToast(`"${newReady.title}" está pronta para cantar!`, 'success', 6000);
                // Recarrega lista de músicas para incluir a nova
                fetchSongs();
            }
        }
        _previousReadyCount = readyCount;

    } catch (e) {
        // Silencioso — rede pode estar temporariamente indisponível
    }
}

// ── Renderização ──
function renderQueueItems(containerId, items) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Filtra apenas itens que não estão "ready" (ou mostra ready por 30s)
    const activeItems = items.filter(i => i.status !== 'ready' || true);

    if (activeItems.length === 0) {
        container.innerHTML = `
            <div class="queue-empty">
                <img class="queue-empty-icon" src="/assets/art/logo-mark.svg" alt="">
                <p>Nada sendo processado agora.</p>
            </div>
        `;
        return;
    }

    // Verifica se precisamos atualizar (evita re-render desnecessário)
    const existingIds = Array.from(container.querySelectorAll('.queue-item-card')).map(el => el.dataset.id);
    const newIds = activeItems.map(i => i.id);
    const needsFullRender = existingIds.length !== newIds.length ||
        !existingIds.every((id, idx) => id === newIds[idx]);

    if (needsFullRender) {
        container.innerHTML = '';
        activeItems.forEach(item => {
            container.appendChild(createQueueItemCard(item));
        });
    } else {
        // Atualiza inline sem re-render
        activeItems.forEach(item => {
            updateQueueItemCard(container, item);
        });
    }
}

function getLyricBadge(item) {
    if (item.has_lrc) {
        return `<span class="chip" data-tone="sage">LRC</span>`;
    } else if (item.has_plain_lyrics) {
        return `<span class="chip" data-tone="blue">Com Letra</span>`;
    } else {
        return `<span class="chip" data-tone="peach">Sem Letra (Whisper)</span>`;
    }
}

function createQueueItemCard(item) {
    const info = STATUS_MAP[item.status] || STATUS_MAP.queued;
    const card = document.createElement('div');
    card.className = 'queue-item-card';
    card.dataset.id = item.id;
    card.dataset.status = item.status;
    card.style.setProperty('--progress', `${item.progress_pct}%`);

    card.innerHTML = `
        <div class="queue-item-icon" data-status="${item.status}">${iconSvg(info.icon)}</div>
        <div class="queue-item-info">
            <div class="queue-item-title">
                ${escapeHtml(item.title || 'Processando...')}
                ${getLyricBadge(item)}
            </div>
            <div class="queue-item-status" data-status="${item.status}">
                ${info.label}${item.error_msg ? ' — ' + escapeHtml(item.error_msg) : ''}
                ${item.added_by ? ` <span class="muted">• ${escapeHtml(item.added_by)}</span>` : ''}
            </div>
        </div>
        <button class="queue-item-remove" data-remove-id="${item.id}" title="Remover da fila" aria-label="Remover da fila">${iconSvg('trash')}</button>
    `;

    // Event: remover
    const removeBtn = card.querySelector('.queue-item-remove');
    if (removeBtn) {
        removeBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await removeFromQueue(item.id);
        });
    }

    return card;
}

function updateQueueItemCard(container, item) {
    const card = container.querySelector(`.queue-item-card[data-id="${item.id}"]`);
    if (!card) return;

    const info = STATUS_MAP[item.status] || STATUS_MAP.queued;

    card.dataset.status = item.status;
    card.style.setProperty('--progress', `${item.progress_pct}%`);

    const iconEl = card.querySelector('.queue-item-icon');
    if (iconEl) {
        iconEl.dataset.status = item.status;
        iconEl.innerHTML = iconSvg(info.icon);
    }

    const titleEl = card.querySelector('.queue-item-title');
    if (titleEl) {
        titleEl.innerHTML = `${escapeHtml(item.title || 'Processando...')} ${getLyricBadge(item)}`;
    }

    const statusEl = card.querySelector('.queue-item-status');
    if (statusEl) {
        statusEl.dataset.status = item.status;
        let text = info.label;
        if (item.error_msg) text += ' — ' + item.error_msg;
        if (item.added_by) text += ` • ${item.added_by}`;
        statusEl.textContent = text;
    }
}


// ── Remoção ──
async function removeFromQueue(itemId) {
    try {
        const resp = await fetch(`/api/queue/remove/${itemId}`, { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Erro ao remover.');
        }
        showToast('Item removido da fila.', 'info');
        await pollQueueStatus();
    } catch (err) {
        showToast('Erro: ' + err.message, 'error');
    }
}

// ── Badges e GPU ──
function updateBadges(items) {
    const activeCount = items.filter(i => i.status !== 'ready' && i.status !== 'error').length;
    const totalCount = items.length;

    // Tab badge (display)
    const tabBadge = document.getElementById('queue-tab-badge');
    if (tabBadge) {
        // vazio = escondido (.tab-badge:empty)
        tabBadge.textContent = activeCount > 0 ? activeCount.toString() : '';
    }
}

function updateGpuBadge(badgeId, textId, isBusy) {
    const badge = document.getElementById(badgeId);
    const text = document.getElementById(textId);
    if (badge) badge.dataset.busy = isBusy ? 'true' : 'false';
    if (text) text.textContent = isBusy ? 'GPU em uso (jogo)' : 'GPU Livre';
}

// ── Utilitários ──

