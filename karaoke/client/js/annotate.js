// Gabarito do cantor: anota cada verso da partida gravada como certo, errado ou
// cantarolei. Fica atrás do lápis discreto da tela de fim de jogo — ferramenta de
// calibração do score, não parte do jogo. Salva em recordings/<id>/gabarito.json.
import { state } from './state.js';
import { iconSvg } from './icons.js';
import { showToast } from './toast.js';
import { openModal, closeModal } from './modal.js';

const LABELS = [
    { value: 'certo', icon: 'check', title: 'Cantei certo' },
    { value: 'errado', icon: 'cross', title: 'Errei a letra' },
    { value: 'cantarolei', icon: 'hum', title: 'Cantarolei / murmurei' },
];

function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

// Mostra o lápis só quando a partida foi gravada (o servidor manda o id no game_over).
export function showAnnotationButton(recordingId) {
    state.annotateRecordingId = recordingId || null;
    const btn = document.getElementById('btn-annotate-verses');
    if (btn) btn.hidden = !state.annotateRecordingId;
}

function renderList(data, player) {
    const list = document.getElementById('annotate-list');
    const labels = (data.labels && data.labels[player]) || {};
    list.replaceChildren();
    for (const verse of data.verses) {
        const row = el('li', 'annotate-row');
        row.dataset.verse = String(verse.n);
        if (labels[verse.n]) row.dataset.label = labels[verse.n];

        const text = el('div', 'annotate-text');
        text.append(el('span', 'annotate-lyrics', `${verse.n}. ${verse.lyrics}`));
        const result = verse.players[player];
        const heard = result
            ? `${formatTime(verse.start)} · nota ${Math.round(result.score)} · ouvi: ${result.heard || '—'}`
            : `${formatTime(verse.start)} · sem áudio`;
        text.append(el('span', 'annotate-heard', heard));

        const choices = el('div', 'annotate-choices');
        for (const { value, icon, title } of LABELS) {
            const btn = el('button', 'annotate-choice');
            btn.innerHTML = iconSvg(icon);
            btn.type = 'button';
            btn.dataset.label = value;
            btn.title = title;
            btn.setAttribute('aria-label', `Verso ${verse.n}: ${title}`);
            btn.setAttribute('aria-pressed', String(labels[verse.n] === value));
            choices.append(btn);
        }
        row.append(text, choices);
        list.append(row);
    }
    updateStatus();
}

function updateStatus() {
    const rows = document.querySelectorAll('#annotate-list .annotate-row');
    const done = [...rows].filter(r => r.dataset.label).length;
    document.getElementById('annotate-status').textContent = `${done}/${rows.length} anotados`;
}

// Celular: cada cantor anota os próprios versos logo depois de cantar.
export function openAnnotationFor(recordingId, player) {
    state.annotateRecordingId = recordingId;
    state.annotateOnlyPlayer = player;
    return openAnnotation();
}

async function openAnnotation() {
    const recordingId = state.annotateRecordingId;
    if (!recordingId) return;
    let data;
    try {
        const res = await fetch(`/api/recordings/${encodeURIComponent(recordingId)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        data = await res.json();
    } catch (e) {
        showToast('Não achei a gravação desta partida.', 'error');
        return;
    }
    state.annotateData = data;

    const select = document.getElementById('annotate-player');
    select.replaceChildren(...data.players.map(p => {
        const opt = el('option', null, p === 'PC_Local' ? 'Local' : p);
        opt.value = p;
        return opt;
    }));
    select.hidden = data.players.length < 2;
    const only = state.annotateOnlyPlayer;
    if (only && data.players.indexOf(only) !== -1) {
        select.value = only;
        select.hidden = true;  // no celular, só o próprio cantor
    }
    state.annotateOnlyPlayer = null;
    document.getElementById('annotate-title').textContent = data.song_title;
    renderList(data, select.value);
    openModal('annotate-modal');
}

async function saveAnnotation() {
    const player = document.getElementById('annotate-player').value;
    const labels = {};
    document.querySelectorAll('#annotate-list .annotate-row').forEach(row => {
        if (row.dataset.label) labels[row.dataset.verse] = row.dataset.label;
    });
    try {
        const res = await fetch(`/api/recordings/${encodeURIComponent(state.annotateRecordingId)}/gabarito`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player, labels }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        state.annotateData.labels = (await res.json()).labels;
        showToast(`Gabarito salvo (${Object.keys(labels).length} versos).`, 'success');
        closeModal('annotate-modal');
    } catch (e) {
        showToast('Falha ao salvar o gabarito.', 'error');
    }
}

export function initAnnotation() {
    const trigger = document.getElementById('btn-annotate-verses');
    if (!trigger) return;
    trigger.addEventListener('click', openAnnotation);
    document.getElementById('btn-annotate-close').addEventListener('click', () => closeModal('annotate-modal'));
    document.getElementById('btn-annotate-save').addEventListener('click', saveAnnotation);
    document.getElementById('annotate-player').addEventListener('change', (e) => {
        if (state.annotateData) renderList(state.annotateData, e.target.value);
    });
    // Tocar de novo no rótulo marcado desmarca o verso.
    document.getElementById('annotate-list').addEventListener('click', (e) => {
        const btn = e.target.closest('.annotate-choice');
        if (!btn) return;
        const row = btn.closest('.annotate-row');
        const label = row.dataset.label === btn.dataset.label ? '' : btn.dataset.label;
        if (label) row.dataset.label = label; else delete row.dataset.label;
        row.querySelectorAll('.annotate-choice').forEach(b => {
            b.setAttribute('aria-pressed', String(b.dataset.label === label));
        });
        updateStatus();
    });
}
