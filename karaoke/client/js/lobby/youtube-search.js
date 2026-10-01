// Busca no YouTube pelo nome da música (passo 1 do "Adicionar música").
//
// O usuário digita o nome, escolhe um resultado e o fluxo segue para o passo 2
// com artista/título já sugeridos. Colar um link direto continua funcionando.

import { state } from '../core/state.js';
import { showToast } from '../core/toast.js';

const YT_URL_RE = /(youtube\.com\/|youtu\.be\/)/i;

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

function formatDuration(sec) {
    if (!sec && sec !== 0) return '';
    const s = Math.round(sec);
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, '0')}`;
}

export function isYoutubeUrl(text) {
    return YT_URL_RE.test(text || '');
}

export function resetYoutubeSearch() {
    state.pickedYoutube = null;
    const input = document.getElementById('youtube-search-input');
    const results = document.getElementById('youtube-results');
    const url = document.getElementById('youtube-vocal-url');
    if (input) input.value = '';
    if (results) results.replaceChildren();
    if (url) url.value = '';
}

function renderMessage(results, text) {
    results.replaceChildren(el('p', 'yt-results__msg', text));
}

async function runSearch(onPick) {
    const input = document.getElementById('youtube-search-input');
    const results = document.getElementById('youtube-results');
    const btn = document.getElementById('btn-youtube-search');
    const query = input.value.trim();

    // Colou um link: usa direto
    if (isYoutubeUrl(query)) {
        onPick({ url: query });
        return;
    }
    if (query.length < 2) {
        showToast('Digite o nome da música ou do artista.', 'error');
        input.focus();
        return;
    }

    btn.disabled = true;
    renderMessage(results, 'Buscando no YouTube...');
    try {
        const resp = await fetch(`/api/youtube-search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Falha na busca');
        const items = data.results || [];
        if (!items.length) {
            renderMessage(results, 'Nada encontrado. Tente outro nome, ou cole o link do vídeo.');
            return;
        }
        results.replaceChildren();
        items.forEach((item) => {
            const row = el('button', 'yt-result');
            row.type = 'button';
            const thumb = el('img', 'yt-result__thumb');
            thumb.src = item.thumbnail;
            thumb.alt = '';
            thumb.loading = 'lazy';
            const info = el('span', 'yt-result__info');
            info.append(
                el('span', 'yt-result__title', item.title),
                el('span', 'yt-result__meta', [item.channel, formatDuration(item.duration)].filter(Boolean).join(' · ')),
            );
            row.append(thumb, info);
            row.addEventListener('click', () => onPick({
                url: item.url,
                artist: item.artist_guess,
                title: item.title_guess,
            }));
            results.append(row);
        });
        const first = results.querySelector('.yt-result');
        if (first && document.documentElement.classList.contains('using-keys')) first.focus();
    } catch (err) {
        renderMessage(results, `Não foi possível buscar agora (${err.message}). Você pode colar o link do vídeo.`);
    } finally {
        btn.disabled = false;
    }
}

// onPick({url, artist?, title?}) — chamado ao escolher um resultado ou colar um link.
export function initYoutubeSearch(onPick) {
    const input = document.getElementById('youtube-search-input');
    const btn = document.getElementById('btn-youtube-search');
    if (!input || !btn) return;

    const pick = (choice) => {
        state.pickedYoutube = choice;
        document.getElementById('youtube-vocal-url').value = choice.url;
        onPick(choice);
    };

    btn.addEventListener('click', () => runSearch(pick));
    // Enter no campo busca (não envia o formulário)
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            runSearch(pick);
        }
    });
}
