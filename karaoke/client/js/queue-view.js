/**
 * queue-view.js — Módulo de Fila de Músicas
 *
 * Gerencia o FAB, bottom sheet, formulário de adição e polling de status.
 * Funciona tanto no modo 'display' (TV) quanto no modo 'mic' (celular).
 */
import { showToast } from './toast.js';
import { fetchSongs, promptGenerationOptions } from './selection-view.js';

// ── Status labels e ícones para cada estado da fila ──
const STATUS_MAP = {
    queued:              { icon: '⏳', label: 'Na fila...' },
    downloading:         { icon: '⬇️', label: 'Baixando do YouTube...' },
    separating:          { icon: '🎛️', label: 'Separando vocal (Demucs GPU)...' },
    awaiting_alignment:  { icon: '⏸️', label: 'Aguardando GPU livre para alinhar...' },
    aligning:            { icon: '🎯', label: 'Alinhando letra (Whisper + MMS)...' },
    finalizing:          { icon: '✨', label: 'Finalizando segmentos...' },
    ready:               { icon: '✅', label: 'Pronta para cantar!' },
    error:               { icon: '❌', label: 'Erro no processamento' },
};

let pollInterval = null;
let isSheetOpen = false;

// ── Inicialização ──
export function initQueueView() {
    const fab = document.getElementById('queue-fab');
    const sheet = document.getElementById('queue-sheet');
    const overlay = document.getElementById('queue-sheet-overlay');
    const closeBtn = document.getElementById('queue-sheet-close');
    const form = document.getElementById('queue-add-form');

    if (!fab || !sheet) return;

    // FAB click → abre sheet
    fab.addEventListener('click', () => openSheet());

    // Fechar sheet
    if (closeBtn) closeBtn.addEventListener('click', () => closeSheet());
    if (overlay) overlay.addEventListener('click', () => closeSheet());

    // Submit do formulário
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await submitToQueue();
        });
    }

    // Botões de destravamento de GPU
    const sheetResetBtn = document.getElementById('queue-sheet-gpu-reset');
    const displayResetBtn = document.getElementById('queue-display-gpu-reset');
    if (sheetResetBtn) {
        sheetResetBtn.addEventListener('click', () => clearGpuLock());
    }
    if (displayResetBtn) {
        displayResetBtn.addEventListener('click', () => clearGpuLock());
    }

    // Inicia polling de status (a cada 3s)
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

// ── Sheet open/close ──
function openSheet() {
    const sheet = document.getElementById('queue-sheet');
    const overlay = document.getElementById('queue-sheet-overlay');
    if (sheet) sheet.setAttribute('data-open', 'true');
    if (overlay) overlay.setAttribute('data-open', 'true');
    isSheetOpen = true;
}

function closeSheet() {
    const sheet = document.getElementById('queue-sheet');
    const overlay = document.getElementById('queue-sheet-overlay');
    if (sheet) sheet.removeAttribute('data-open');
    if (overlay) overlay.removeAttribute('data-open');
    isSheetOpen = false;
}

// ── Envio para a fila ──
async function submitToQueue() {
    const urlInput = document.getElementById('queue-yt-url');
    const langSelect = document.getElementById('queue-language');
    const addedByInput = document.getElementById('queue-added-by');
    const submitBtn = document.getElementById('queue-submit-btn');

    const ytUrl = urlInput?.value?.trim();
    if (!ytUrl) {
        showToast('Cole o link do YouTube primeiro!', 'error');
        return;
    }

    if (!ytUrl.includes('youtube.com') && !ytUrl.includes('youtu.be')) {
        showToast('Insira uma URL válida do YouTube.', 'error');
        return;
    }

    // Fecha a aba da fila para exibir o modal de opções de geração limpo na tela
    closeSheet();
    const choice = await promptGenerationOptions();
    if (!choice) {
        // Se o usuário fechar/cancelar, reabre a aba da fila e aborta
        openSheet();
        return;
    }

    const alignLyrics = (choice === 'pro');

    // Disable button
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = '⏳ Adicionando...';
    }

    try {
        // plain_lyrics vazio = backend vai auto-fetch via LRCLIB/Lyrics.ovh
        const params = new URLSearchParams({
            youtube_url: ytUrl,
            language: langSelect?.value || 'en',
            plain_lyrics: '',
            added_by: addedByInput?.value?.trim() || '',
            align_lyrics: alignLyrics.toString(),
        });

        const resp = await fetch('/api/queue/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: params.toString(),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Erro ao adicionar à fila.');
        }

        const data = await resp.json();
        showToast(data.message || 'Música adicionada à fila!', 'success');

        // Limpa formulário
        if (urlInput) urlInput.value = '';

        // Atualiza imediatamente
        await pollQueueStatus();

    } catch (err) {
        showToast('Erro: ' + err.message, 'error');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = '➕ Adicionar à Fila';
        }
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

async function pollQueueStatus() {
    try {
        const resp = await fetch('/api/queue/status');
        if (!resp.ok) return;
        const data = await resp.json();

        const items = data.queue || [];
        const gpuBusy = data.gpu_busy || false;

        // Renderiza nos dois locais: bottom sheet e aba display
        renderQueueItems('queue-items-list', items);
        renderQueueItems('queue-display-list', items);

        // Atualiza badges de contagem
        updateBadges(items);

        // Atualiza indicadores de GPU
        updateGpuBadge('queue-sheet-gpu-badge', 'queue-sheet-gpu-text', gpuBusy);
        updateGpuBadge('queue-display-gpu-badge', 'queue-display-gpu-text', gpuBusy);

        const sheetResetBtn = document.getElementById('queue-sheet-gpu-reset');
        const displayResetBtn = document.getElementById('queue-display-gpu-reset');
        if (sheetResetBtn) sheetResetBtn.style.display = gpuBusy ? 'inline-block' : 'none';
        if (displayResetBtn) displayResetBtn.style.display = gpuBusy ? 'inline-block' : 'none';

        // Notifica quando música ficou pronta
        const readyCount = items.filter(i => i.status === 'ready').length;
        if (readyCount > _previousReadyCount && _previousReadyCount >= 0) {
            const newReady = items.filter(i => i.status === 'ready').slice(-1)[0];
            if (newReady) {
                showToast(`🎉 "${newReady.title}" está pronta para cantar!`, 'success', 6000);
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
                <div class="queue-empty-icon">🎶</div>
                <p>Nenhuma música na fila ainda.<br>Cole um link do YouTube acima!</p>
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
        return `<span style="font-size: 0.7rem; font-weight: 700; color: #10b981; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); padding: 0.15rem 0.4rem; border-radius: 4px; margin-left: 0.5rem; display: inline-block; vertical-align: middle;">LRC</span>`;
    } else if (item.has_plain_lyrics) {
        return `<span style="font-size: 0.7rem; font-weight: 700; color: #38bdf8; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); padding: 0.15rem 0.4rem; border-radius: 4px; margin-left: 0.5rem; display: inline-block; vertical-align: middle;">Com Letra</span>`;
    } else {
        return `<span style="font-size: 0.7rem; font-weight: 700; color: #f59e0b; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.25); padding: 0.15rem 0.4rem; border-radius: 4px; margin-left: 0.5rem; display: inline-block; vertical-align: middle;">Sem Letra (Whisper)</span>`;
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
        <div class="queue-item-icon" data-status="${item.status}">${info.icon}</div>
        <div class="queue-item-info">
            <div class="queue-item-title">
                ${escapeHtml(item.title || 'Processando...')}
                ${getLyricBadge(item)}
            </div>
            <div class="queue-item-status" data-status="${item.status}">
                ${info.label}${item.error_msg ? ' — ' + escapeHtml(item.error_msg) : ''}
                ${item.added_by ? ` <span style="opacity: 0.5;">• ${escapeHtml(item.added_by)}</span>` : ''}
            </div>
        </div>
        <button class="queue-item-remove" data-remove-id="${item.id}" title="Remover da fila">🗑️</button>
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
        iconEl.textContent = info.icon;
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

    // FAB badge
    const fabBadge = document.getElementById('queue-fab-badge');
    if (fabBadge) {
        fabBadge.dataset.count = activeCount.toString();
        fabBadge.textContent = activeCount > 0 ? activeCount.toString() : '';
    }

    // Tab badge (display)
    const tabBadge = document.getElementById('queue-tab-badge');
    if (tabBadge) {
        if (activeCount > 0) {
            tabBadge.style.display = 'inline';
            tabBadge.textContent = activeCount.toString();
        } else {
            tabBadge.style.display = 'none';
        }
    }
}

function updateGpuBadge(badgeId, textId, isBusy) {
    const badge = document.getElementById(badgeId);
    const text = document.getElementById(textId);
    if (badge) badge.dataset.busy = isBusy ? 'true' : 'false';
    if (text) text.textContent = isBusy ? 'GPU em uso (jogo)' : 'GPU Livre';
}

// ── Utilitários ──
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
