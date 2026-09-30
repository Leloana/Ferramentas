// Painel de saúde: clicar no "Online" do cabeçalho. Atualiza a cada 2 s
// enquanto aberto — serve para ver na hora por que a nota atrasou na festa.
import { openModal } from './modal.js';

const REFRESH_MS = 2000;

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

function row(label, value, tone) {
    const r = el('div', 'status-row');
    if (tone) r.dataset.tone = tone;
    r.append(el('span', 'status-row__label', label), el('span', 'status-row__value', value));
    return r;
}

function secs(v) {
    return typeof v === 'number' ? `${v.toFixed(1)} s` : '—';
}

function render(view, data) {
    view.replaceChildren();
    const gpu = el('section', 'status-block');
    gpu.append(el('h4', 'status-block__title', 'GPU'),
        row('Whisper', data.gpu.whisper_model),
        row('Ocupada', data.gpu.locked ? 'sim' : 'não', data.gpu.locked ? 'warn' : 'ok'),
        row('Partida em curso', data.gpu.game_active ? 'sim' : 'não'));
    const queue = el('section', 'status-block');
    queue.append(el('h4', 'status-block__title', 'Fila'), row('Itens', String(data.queue.total)));
    Object.keys(data.queue.by_status || {}).forEach((s) => queue.append(row(s, String(data.queue.by_status[s]))));
    view.append(gpu, queue);

    (data.rooms || []).forEach((room) => {
        const block = el('section', 'status-block');
        const slow = typeof room.verse_latency_p90 === 'number' && room.verse_latency_p90 > 3;
        block.append(el('h4', 'status-block__title', `Sala ${room.id}`),
            row('Música', room.song || '—'),
            row('TV', room.display ? 'conectada' : 'desconectada', room.display ? 'ok' : 'warn'),
            row('Celulares', room.players.length ? room.players.join(', ') : 'nenhum'),
            row('Na fila de apelido', String(room.waiting_mics)),
            row('Versos na fila da GPU', String(room.pending_verses), room.pending_verses > 2 ? 'warn' : null),
            row('Tempo até a nota (mediana)', secs(room.verse_latency_median)),
            row('Tempo até a nota (90%)', secs(room.verse_latency_p90), slow ? 'warn' : null));
        view.append(block);
    });

    const disk = el('section', 'status-block');
    disk.append(el('h4', 'status-block__title', 'Disco'),
        row('Livre', `${data.disk.free_gb} GB de ${data.disk.total_gb} GB`, data.disk.free_gb < 5 ? 'warn' : 'ok'),
        row('Músicas', String(data.songs)));
    view.append(disk);
}

async function refresh(view) {
    try {
        const resp = await fetch('/api/status');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        render(view, await resp.json());
    } catch (e) {
        view.replaceChildren(el('p', 'profile-empty', `Servidor sem resposta (${e.message})`));
    }
}

export function initStatusPanel() {
    const trigger = document.querySelector('.header-status');
    const modal = document.getElementById('status-modal');
    const view = document.getElementById('status-view');
    if (!trigger || !modal || !view) return;
    trigger.setAttribute('role', 'button');
    trigger.tabIndex = 0;
    let timer = null;
    const open = () => {
        openModal(modal, {
            onClose: () => { clearInterval(timer); timer = null; },
        });
        refresh(view);
        timer = setInterval(() => refresh(view), REFRESH_MS);
    };
    trigger.addEventListener('click', open);
    trigger.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(); });
}
