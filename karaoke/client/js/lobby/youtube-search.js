// Busca no YouTube pelo nome da música (passo 1 do "Adicionar música").
//
// O usuário digita o nome, escolhe um resultado e o fluxo segue para o passo 2
// com artista/título já sugeridos. Colar um link direto continua funcionando;
// link de playlist abre a lista de músicas (playlist-import.js).

import { state } from '../core/state.js';
import { showToast } from '../core/toast.js';
import { iconSvg } from '../core/icons.js';
import { isPlaylistUrl } from './playlist-import.js';

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

// Fecha a prévia aberta (se houver) sem tocar no resto da busca. Chamado ao
// escolher um resultado, buscar de novo ou fechar o modal — senão o áudio do
// vídeo embutido continua tocando escondido.
export function stopYoutubePreview() {
    const results = document.getElementById('youtube-results');
    if (!results) return;
    closeAllPreviews(results);
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

// Remove qualquer prévia aberta dentro de `results` e devolve os botões de
// play ao estado inicial. Só uma prévia toca por vez.
function closeAllPreviews(results) {
    results.querySelectorAll('.yt-result__preview').forEach((panel) => panel.remove());
    results.querySelectorAll('.yt-result__play').forEach((btn) => {
        btn.innerHTML = iconSvg('play');
        btn.setAttribute('aria-label', 'Ouvir prévia');
        btn.title = 'Ouvir prévia';
    });
}

function openPreview(itemEl, playBtn, videoId) {
    const panel = el('div', 'yt-result__preview');
    const frame = document.createElement('iframe');
    frame.className = 'yt-result__preview-frame';
    frame.src = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
    frame.title = 'Prévia do vídeo';
    frame.allow = 'autoplay; encrypted-media';
    frame.setAttribute('frameborder', '0');
    panel.append(frame);
    itemEl.append(panel);
    playBtn.innerHTML = iconSvg('close');
    playBtn.setAttribute('aria-label', 'Fechar prévia');
    playBtn.title = 'Fechar prévia';
}

async function runSearch(onPick, onPlaylist) {
    const input = document.getElementById('youtube-search-input');
    const results = document.getElementById('youtube-results');
    const btn = document.getElementById('btn-youtube-search');
    const query = input.value.trim();
    closeAllPreviews(results);

    // Colou link de playlist: escolhe várias de uma vez
    if (isPlaylistUrl(query) && onPlaylist) {
        onPlaylist(query);
        return;
    }
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
            const itemEl = el('div', 'yt-result');

            const playBtn = el('button', 'yt-result__play');
            playBtn.type = 'button';
            playBtn.innerHTML = iconSvg('play');
            playBtn.setAttribute('aria-label', 'Ouvir prévia');
            playBtn.title = 'Ouvir prévia';
            playBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const wasOpen = !!itemEl.querySelector('.yt-result__preview');
                closeAllPreviews(results);
                if (!wasOpen && item.id) openPreview(itemEl, playBtn, item.id);
            });

            const main = el('button', 'yt-result__main');
            main.type = 'button';
            const thumb = el('img', 'yt-result__thumb');
            thumb.src = item.thumbnail;
            thumb.alt = '';
            thumb.loading = 'lazy';
            const info = el('span', 'yt-result__info');
            info.append(
                el('span', 'yt-result__title', item.title),
                el('span', 'yt-result__meta', [item.channel, formatDuration(item.duration)].filter(Boolean).join(' · ')),
            );
            main.append(thumb, info);
            main.addEventListener('click', () => {
                closeAllPreviews(results);
                onPick({
                    url: item.url,
                    artist: item.artist_guess,
                    title: item.title_guess,
                    duration: item.duration,  // tempo estimado da fila já ao adicionar
                });
            });

            itemEl.append(playBtn, main);
            results.append(itemEl);
        });
        const first = results.querySelector('.yt-result__main');
        if (first && document.documentElement.classList.contains('using-keys')) first.focus();
    } catch (err) {
        renderMessage(results, `Não foi possível buscar agora (${err.message}). Você pode colar o link do vídeo.`);
    } finally {
        btn.disabled = false;
    }
}

// onPick({url, artist?, title?}) — chamado ao escolher um resultado ou colar um link.
// onPlaylist(url) — chamado ao colar o link de uma playlist.
export function initYoutubeSearch(onPick, onPlaylist) {
    const input = document.getElementById('youtube-search-input');
    const btn = document.getElementById('btn-youtube-search');
    if (!input || !btn) return;

    const pick = (choice) => {
        state.pickedYoutube = choice;
        document.getElementById('youtube-vocal-url').value = choice.url;
        onPick(choice);
    };

    btn.addEventListener('click', () => runSearch(pick, onPlaylist));
    // Enter no campo busca (não envia o formulário)
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            runSearch(pick, onPlaylist);
        }
    });
}
