import { state, setAppState } from './state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from './dom.js';
import { showToast } from './toast.js';
import { openModal, closeModal } from './modal.js';
import { initTabs } from './tabs.js';
import { ensureDefaultSeat } from './lobby.js';

export async function fetchSongs() {
    try {
        dom.songListEl.innerHTML = `
            <div class="song-list__loading">
                <div class="spinner spinner--sm"></div>
                Carregando músicas...
            </div>
        `;

        const resp = await fetch('/api/songs');
        const songs = await resp.json();

        // Ordena alfabeticamente pelo título respeitando acentos e ignorando maiúsculas/minúsculas
        songs.sort((a, b) => a.title.localeCompare(b.title, 'pt-BR', { sensitivity: 'base' }));

        state.allSongs = songs;

        document.getElementById('search-input').value = '';
        renderArtistGroups(songs);
    } catch (e) {
        dom.songListEl.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--error)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>
                <h4 class="form-error">Erro ao conectar com o servidor</h4>
                <p>Certifique-se de que o backend está rodando localmente.</p>
                <button id="btn-retry-fetch-songs" class="btn btn--danger">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg>
                    Tentar Novamente
                </button>
            </div>
        `;
        const retry = document.getElementById('btn-retry-fetch-songs');
        if (retry) retry.addEventListener('click', fetchSongs);
        showToast("Não foi possível conectar ao servidor", "error");
    }
}

/* ── Fuzzy Artist Grouping ────────────────────────────────────── */

function normalizeArtist(name) {
    if (!name) return '';
    return name
        .normalize('NFD')
        .replace(/[̀-ͯ]/g, '')
        .toLowerCase()
        .trim()
        .replace(/\s+/g, ' ');
}

function artistSimilarity(a, b) {
    const na = normalizeArtist(a);
    const nb = normalizeArtist(b);
    if (na === nb) return true;

    // Se um contém o outro completamente, considera similar
    if (na.includes(nb) || nb.includes(na)) return true;

    // Interseção de palavras > 50%
    const wordsA = na.split(/\s+/);
    const wordsB = nb.split(/\s+/);
    const shorter = wordsA.length <= wordsB.length ? wordsA : wordsB;
    const longer = wordsA.length <= wordsB.length ? wordsB : wordsA;
    const intersection = shorter.filter(w => longer.includes(w));
    if (intersection.length / shorter.length >= 0.5) return true;

    return false;
}

function groupSongsByArtist(songs) {
    const groups = [];

    songs.forEach(song => {
        const artist = song.artist || "Artista Desconhecido";
        // Procura grupo existente por similaridade
        let group = null;
        for (const g of groups) {
            if (artistSimilarity(artist, g.artist)) {
                group = g;
                break;
            }
        }
        if (!group) {
            group = { artist, songs: [] };
            groups.push(group);
        }
        group.songs.push(song);
    });

    // Ordena artistas alfabeticamente (pelo primeiro nome normalizado)
    groups.sort((a, b) => normalizeArtist(a.artist).localeCompare(normalizeArtist(b.artist)));

    // Dentro de cada grupo, ordena músicas pelo título
    groups.forEach(g =>
        g.songs.sort((a, b) => a.title.localeCompare(b.title, 'pt-BR', { sensitivity: 'base' }))
    );

    return groups;
}

/* ── Artist-Grouped Rendering ─────────────────────────────────── */

// Abre/fecha um grupo animando a altura real do conteúdo (não um max-height
// gigante, que dava a "travada" ao fechar).
function toggleArtistGroup(groupDiv, header) {
    const songs = groupDiv.querySelector('.artist-group__songs');
    const opening = !groupDiv.classList.contains('artist-group--open');
    header.setAttribute('aria-expanded', String(opening));
    clearTimeout(songs._settle);

    // parte sempre de um valor em px (de "none" não dá para animar)
    songs.style.maxHeight = (opening ? 0 : songs.scrollHeight) + 'px';
    songs.offsetHeight; // aplica o ponto de partida antes de mudar
    groupDiv.classList.toggle('artist-group--open', opening);
    songs.style.maxHeight = (opening ? songs.scrollHeight : 0) + 'px';

    // fim da animação: aberto volta a "sem limite". Temporizador em vez de
    // transitionend, que nem sempre dispara (aba em segundo plano, TV lenta).
    songs._settle = setTimeout(() => {
        if (groupDiv.classList.contains('artist-group--open')) songs.style.maxHeight = 'none';
    }, 260);
}

// Com poucos artistas (ou numa busca) os grupos já abrem: menos cliques no controle da TV.
const AUTO_EXPAND_MAX_GROUPS = 3;

export function renderArtistGroups(songsList, { expandAll = false } = {}) {
    dom.songListEl.innerHTML = '';

    if (songsList.length === 0) {
        dom.songListEl.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--dim)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>
                <h4>Nenhuma música encontrada</h4>
                <p>Tente buscar por outro termo ou adicione arquivos na pasta <code>server/songs/</code>!</p>
            </div>
        `;
        return;
    }

    const groups = groupSongsByArtist(songsList);
    const tpl = document.getElementById('song-card-tpl');
    const openGroups = expandAll || groups.length <= AUTO_EXPAND_MAX_GROUPS;

    // Duas colunas independentes: 1ª metade (A→…) à esquerda, 2ª à direita.
    // Abrir um grupo não empurra a outra coluna (em tela estreita elas empilham).
    const columns = [document.createElement('div'), document.createElement('div')];
    columns.forEach((col) => { col.className = 'song-list__col'; dom.songListEl.appendChild(col); });
    const half = Math.ceil(groups.length / 2);

    groups.forEach((group, groupIdx) => {
        // Container do artista
        const groupDiv = document.createElement('div');
        groupDiv.className = openGroups ? 'artist-group artist-group--open' : 'artist-group';

        // Header do artista
        const header = document.createElement('div');
        header.className = 'artist-group__header';
        header.tabIndex = 0;
        header.setAttribute('role', 'button');
        header.innerHTML = `
            <svg class="artist-group__chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
            <span class="artist-group__name"></span>
            <span class="artist-group__count">${group.songs.length}</span>
        `;
        header.querySelector('.artist-group__name').textContent = group.artist;
        header.setAttribute('aria-expanded', String(openGroups));
        header.addEventListener('click', () => toggleArtistGroup(groupDiv, header));
        groupDiv.appendChild(header);

        // Grid de músicas
        const songsGrid = document.createElement('div');
        songsGrid.className = 'artist-group__songs';

        group.songs.forEach(song => {
            const frag = tpl.content.cloneNode(true);
            const card = frag.querySelector('.song-card');
            const titleEl = frag.querySelector('.song-card__title');
            const artistEl = frag.querySelector('.song-card__artist');
            const editBtn = frag.querySelector('.song-card__edit-btn');
            const deleteBtn = frag.querySelector('.song-card__delete-btn');

            titleEl.innerText = song.title;
            artistEl.innerText = song.artist || "Artista Desconhecido";

            if (song.is_ready === false) {
                // Música pendente: sem clique para jogar, com badge. Mantém só o reinstalar.
                card.classList.add('song-card--pending');
                card.removeAttribute('role');
                card.tabIndex = -1;

                const badge = document.createElement('span');
                badge.innerText = 'Pendente';
                badge.className = 'chip';
                badge.dataset.tone = 'peach';
                titleEl.appendChild(badge);

                // Música ainda processando: sem editar/apagar
                if (editBtn) editBtn.remove();
                if (deleteBtn) deleteBtn.remove();
            } else {
                // Música pronta: comportamento normal
                card.addEventListener('click', () => selectSong(song));

                editBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    loadAndOpenLrcEditor(song.id);
                });

                deleteBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (confirm(`Tem certeza que deseja excluir permanentemente a música "${song.title}"? Todos os arquivos de áudio, letras e segmentos serão apagados do servidor!`)) {
                        try {
                            const resp = await fetch(`/api/delete-song/${song.id}`, { method: 'DELETE' });
                            if (!resp.ok) {
                                const err = await resp.json();
                                throw new Error(err.detail || "Erro ao excluir música");
                            }
                            showToast(`Música "${song.title}" excluída com sucesso!`, "success");
                            fetchSongs();
                        } catch (err) {
                            showToast(`Erro ao excluir música: ${err.message}`, "error");
                        }
                    }
                });
            }

            songsGrid.appendChild(frag);
        });

        groupDiv.appendChild(songsGrid);
        columns[groupIdx < half ? 0 : 1].appendChild(groupDiv);
    });
}

// Capa do álbum no lobby (GET /api/songs/<id>/cover); some se não houver
function showSongCover(songId) {
    const img = document.getElementById('current-song-cover');
    if (!img) return;
    img.hidden = true;
    img.onload = () => { img.hidden = false; };
    img.onerror = () => { img.hidden = true; };
    img.src = `/api/songs/${encodeURIComponent(songId)}/cover`;
}

export function selectSong(song) {
    state.selectedSongId = song.id;
    document.getElementById('current-song-title').innerText = song.title;
    document.getElementById('current-song-artist').innerText = song.artist || '';
    showSongCover(song.id);
    setAppState('waiting');
    ensureDefaultSeat();
    dom.audioPlayer.src = `/songs/${song.id}/audio`;

    const savedVolume = localStorage.getItem('karaoke_backing_volume');
    if (savedVolume !== null) {
        const vol = parseFloat(savedVolume);
        if (state.audioManager) {
            state.audioManager.setVolume(vol);
        } else {
            dom.audioPlayer.volume = vol;
        }
    }
}

export async function loadAndOpenLrcEditor(slug) {
    const gen = startLoadingOverlay("Carregando Letras...", "Buscando informações no servidor...");

    try {
        const resp = await fetch(`/api/get-lyrics?slug=${encodeURIComponent(slug)}&t=${Date.now()}`, {
            headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });
        if (!resp.ok) throw new Error("Não foi possível carregar os dados");
        const data = await resp.json();

        stopLoadingOverlay(gen);

        if (data.success) {
            document.getElementById('editor-slug').value = slug;
            document.getElementById('editor-language').value = data.language;
            document.getElementById('editor-textarea').value = data.lyrics || '';

            // Parse meta JSON para popular campos
            let metaParsed = null;
            try {
                metaParsed = JSON.parse(data.meta_json || '{}');
            } catch (e) {
                metaParsed = null;
            }

            // Popula o textarea oculto com o JSON completo (compatibilidade interna)
            const metaArea = document.getElementById('editor-meta-textarea');
            if (metaArea) {
                metaArea.value = data.meta_json || '';
            }

            // Popula os campos editáveis da aba Meta
            const metaTitle = document.getElementById('editor-meta-title');
            const metaArtist = document.getElementById('editor-meta-artist');
            const metaLanguage = document.getElementById('editor-meta-language');
            const metaYoutube = document.getElementById('editor-meta-youtube');
            const metaInfo = (metaParsed && metaParsed.meta) || {};
            const metaAudio = (metaParsed && metaParsed.audio) || {};
            const metaLyrics = (metaParsed && metaParsed.lyrics) || {};
            const ytUrl = metaAudio.youtube_vocal_url || metaAudio.youtube_backing_url || '';
            if (metaTitle) metaTitle.value = metaInfo.title || '';
            if (metaArtist) metaArtist.value = metaInfo.artist || '';
            if (metaYoutube) metaYoutube.value = ytUrl;
            if (metaLanguage) {
                const lang = metaInfo.language || 'pt';
                // Tenta selecionar a opção correspondente; se não existir, adiciona dinamicamente
                // via .value: o select personalizado (select.js) acompanha
                const found = Array.prototype.some.call(metaLanguage.options, (opt) => opt.value === lang);
                if (found) metaLanguage.value = lang;
                if (!found && lang) {
                    const newOpt = document.createElement('option');
                    newOpt.value = lang;
                    newOpt.textContent = lang;
                    metaLanguage.insertBefore(newOpt, metaLanguage.lastElementChild);
                    metaLanguage.value = lang;
                }
            }

            // Reabre sempre na aba de ajustes (meta.json)
            const btnTabMeta = document.getElementById('btn-tab-meta');
            if (btnTabMeta) btnTabMeta.click();

            // Popula a área de texto de colar letra
            const pasteArea = document.getElementById('editor-paste-lyrics-textarea');
            if (pasteArea) {
                pasteArea.value = metaLyrics.plain_lyrics || '';
            }

            // Popula link do YouTube
            const ytLinksDiv = document.getElementById('editor-youtube-links');
            const ytLink = document.getElementById('editor-youtube-vocal-link');
            if (ytLinksDiv && ytLink) {
                if (ytUrl) ytLink.href = ytUrl;
                ytLinksDiv.hidden = !ytUrl;
            }

            openModal(dom.lrcEditorModal);
        } else {
            showToast("Erro: Os arquivos da música não foram localizados no servidor.", "error");
        }
    } catch (e) {
        stopLoadingOverlay(gen);
        showToast("Erro ao carregar os dados da música: " + e.message, "error");
    }
}

export function initSearch() {
    const input = document.getElementById('search-input');
    if (!input) return;

    const normalizeText = (str) => {
        return str ? str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase() : "";
    };

    input.oninput = (e) => {
        const query = normalizeText(e.target.value);
        const filtered = state.allSongs.filter(song =>
            normalizeText(song.title).includes(query) ||
            normalizeText(song.artist).includes(query)
        );
        renderArtistGroups(filtered, { expandAll: query.length > 0 });
    };

    initSelectionTabs();
}

export function initSelectionTabs() {
    initTabs('selection-area', {});
}

export function promptGenerationOptions() {
    return new Promise((resolve) => {
        const modal = document.getElementById('generation-options-modal');
        const btnPro = document.getElementById('btn-gen-pro');
        const btnFlash = document.getElementById('btn-gen-flash');
        const btnClose = document.getElementById('btn-close-gen-options');

        if (!modal || !btnPro || !btnFlash || !btnClose) {
            resolve(null);
            return;
        }

        let settled = false;
        const settle = (choice) => {
            if (settled) return;
            settled = true;
            btnPro.onclick = null;
            btnFlash.onclick = null;
            btnClose.onclick = null;
            resolve(choice);
        };

        // Botões resolvem com a escolha; fechar (X, ESC, clique fora, voltar) resolve null.
        const cleanupAndResolve = (choice) => {
            settle(choice);
            closeModal(modal);
        };

        btnPro.onclick = () => cleanupAndResolve('pro');
        btnFlash.onclick = () => cleanupAndResolve('flash');
        btnClose.onclick = () => cleanupAndResolve(null);

        openModal(modal, { onClose: () => settle(null) });
    });
}
