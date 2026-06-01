import { state, setAppState } from './state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from './dom.js';
import { showToast } from './toast.js';
import { openModal, closeModal } from './modal.js';
import { initTabs } from './tabs.js';

export async function fetchSongs() {
    try {
        dom.songListEl.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--dim);">
                <div style="width: 32px; height: 32px; border: 3px solid #1e293b; border-top: 3px solid var(--accent); border-radius: 50%; margin: 0 auto 1rem; animation: spin 1s linear infinite;"></div>
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
        renderReinstallList(songs);
    } catch (e) {
        dom.songListEl.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--error)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>
                <h4 style="color: var(--error)">Erro ao conectar com o servidor</h4>
                <p>Certifique-se de que o backend está rodando localmente.</p>
                <button id="btn-retry-fetch-songs" class="btn-icon-text" style="margin: 1.5rem auto 0 auto; border-color: rgba(239, 68, 68, 0.4); color: var(--error); padding: 0.5rem 1.2rem;">
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

export function renderArtistGroups(songsList) {
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

    groups.forEach(group => {
        // Container do artista
        const groupDiv = document.createElement('div');
        groupDiv.className = 'artist-group';

        // Header do artista
        const header = document.createElement('div');
        header.className = 'artist-group__header';
        header.innerHTML = `
            <svg class="artist-group__chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
            <span class="artist-group__name">${group.artist}</span>
            <span class="artist-group__count">${group.songs.length}</span>
        `;
        header.addEventListener('click', () => {
            groupDiv.classList.toggle('artist-group--open');
        });
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
                // Música pendente: sem clique para jogar, com badge e botão reinstalar
                card.style.cursor = 'default';
                card.style.opacity = '0.7';

                const badge = document.createElement('span');
                badge.innerText = 'Pendente';
                badge.style.cssText = 'font-size: 0.7rem; font-weight: 700; color: #f97316; background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.25); padding: 0.15rem 0.4rem; border-radius: 4px; margin-left: 0.5rem; display: inline-block; vertical-align: middle;';
                artistEl.appendChild(badge);

                // Remove edit/delete, adiciona reinstalar
                if (editBtn) editBtn.remove();
                if (deleteBtn) deleteBtn.remove();

                const reinstallBtn = document.createElement('button');
                reinstallBtn.type = 'button';
                reinstallBtn.className = 'song-card__reinstall-btn';
                reinstallBtn.title = 'Reinstalar Música';
                reinstallBtn.innerHTML = '🔄';
                reinstallBtn.style.cssText = 'background: transparent; border: none; font-size: 1.25rem; padding: 0.25rem 0.5rem; cursor: pointer; transition: transform 0.3s ease;';

                reinstallBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    triggerReinstall(song.id, song.title);
                });
                reinstallBtn.addEventListener('mouseenter', () => { reinstallBtn.style.transform = 'rotate(180deg)'; });
                reinstallBtn.addEventListener('mouseleave', () => { reinstallBtn.style.transform = 'rotate(0deg)'; });

                const actionsDiv = document.createElement('div');
                actionsDiv.style.cssText = 'display: flex; align-items: center; gap: 0.5rem;';
                actionsDiv.appendChild(reinstallBtn);
                card.appendChild(actionsDiv);
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
        dom.songListEl.appendChild(groupDiv);
    });
}

export function selectSong(song) {
    state.selectedSongId = song.id;
    document.getElementById('current-song-title').innerText = song.title;
    setAppState('waiting');
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
            if (metaTitle) metaTitle.value = metaParsed?.meta?.title || '';
            if (metaArtist) metaArtist.value = metaParsed?.meta?.artist || '';
            if (metaYoutube) metaYoutube.value = metaParsed?.audio?.youtube_vocal_url || metaParsed?.audio?.youtube_backing_url || '';
            if (metaLanguage) {
                const lang = metaParsed?.meta?.language || 'pt';
                // Tenta selecionar a opção correspondente; se não existir, adiciona dinamicamente
                let found = false;
                for (const opt of metaLanguage.options) {
                    if (opt.value === lang) { opt.selected = true; found = true; break; }
                }
                if (!found && lang) {
                    const newOpt = document.createElement('option');
                    newOpt.value = lang;
                    newOpt.textContent = lang;
                    metaLanguage.insertBefore(newOpt, metaLanguage.lastElementChild);
                    metaLanguage.value = lang;
                }
            }

            if (dom.lrcEditorForm) {
                dom.lrcEditorForm.setAttribute('data-editor-tab', 'meta');
            }

            // Popula a área de texto de colar letra
            const pasteArea = document.getElementById('editor-paste-lyrics-textarea');
            if (pasteArea) {
                pasteArea.value = metaParsed?.lyrics?.plain_lyrics || '';
            }

            // Popula link do YouTube
            const ytLinksDiv = document.getElementById('editor-youtube-links');
            const ytLink = document.getElementById('editor-youtube-vocal-link');
            if (ytLinksDiv && ytLink) {
                const ytUrl = metaParsed?.audio?.youtube_vocal_url || metaParsed?.audio?.youtube_backing_url || '';
                if (ytUrl) {
                    ytLink.href = ytUrl;
                    ytLinksDiv.style.display = 'block';
                } else {
                    ytLinksDiv.style.display = 'none';
                }
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
        renderArtistGroups(filtered);
    };

    initSelectionTabs();
}

export async function triggerReinstall(songId, songTitle) {
    if (dom.lrcEditorModal) closeModal(dom.lrcEditorModal);

    // Procura a música no state para pegar o artista correto
    const song = state.allSongs?.find(s => s.id === songId);
    const artist = song ? song.artist : '';
    const title = song ? song.title : songTitle;

    let hasSyncedLrc = false;

    // Busca rápida de preview de letra
    try {
        const lyricsRes = await fetch(`/api/fetch-lyrics?artist=${encodeURIComponent(artist)}&track=${encodeURIComponent(title)}`);
        const lyricsData = await lyricsRes.json();
        if (lyricsData.success && lyricsData.syncedLyrics) {
            hasSyncedLrc = true;
        }
    } catch (err) {
        console.error('Erro ao verificar letras na API para reinstall:', err);
    }

    let choice = null;
    if (hasSyncedLrc) {
        // Se encontrou o .lrc via API, não abre o modal de escolha pro/flash!
        // Segue direto para o reinstall (align_lyrics = false, pois usará o .lrc da API).
        choice = 'flash'; 
    } else {
        // Caso contrário, abre o modal de escolha
        choice = await promptGenerationOptions();
        if (!choice) {
            if (dom.lrcEditorModal && document.getElementById('editor-slug')?.value === songId) {
                openModal(dom.lrcEditorModal);
            }
            return;
        }
    }

    const alignLyrics = (choice === 'pro');

    const gen = startLoadingOverlay("Reinstalando...", "Executando processo de download, separação Demucs (GPU) e alinhamento Whisper... 🔄🎧", true);

    try {
        const body = new URLSearchParams({
            title,
            artist,
            align_lyrics: alignLyrics,
            clean_existing: 'true',
        });

        const response = await fetch(`/api/queue/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString(),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Erro ao reinstalar");
        }

        const data = await response.json();
        stopLoadingOverlay(gen);
        showToast(data.message || "Música adicionada à fila para reinstalação!", "success");
        
        // Abre a aba da Fila para o usuário acompanhar o progresso
        const queueTabBtn = document.getElementById('tab-btn-queue');
        if (queueTabBtn) queueTabBtn.click();

    } catch (error) {
        stopLoadingOverlay(gen);
        showToast("Erro ao reinstalar: " + error.message, "error");
        if (dom.lrcEditorModal && document.getElementById('editor-slug')?.value === songId) {
            openModal(dom.lrcEditorModal);
        }
    }
}

export function renderReinstallList(songsList) {
    const reinstallListEl = document.getElementById('reinstall-list');
    if (!reinstallListEl) return;
    reinstallListEl.innerHTML = '';

    if (songsList.length === 0) {
        reinstallListEl.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--dim)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>
                <h4>Nenhuma música encontrada</h4>
            </div>
        `;
        return;
    }

    const tpl = document.getElementById('song-card-tpl');
    songsList.forEach(song => {
        const frag = tpl.content.cloneNode(true);
        const card = frag.querySelector('.song-card');
        const titleEl = frag.querySelector('.song-card__title');
        const artistEl = frag.querySelector('.song-card__artist');
        
        const editBtn = frag.querySelector('.song-card__edit-btn');
        const deleteBtn = frag.querySelector('.song-card__delete-btn');
        if (editBtn) editBtn.remove();
        if (deleteBtn) deleteBtn.remove();

        titleEl.innerText = song.title;
        artistEl.innerText = song.artist || "Artista Desconhecido";

        if (song.is_ready === false) {
            const badge = document.createElement('span');
            badge.innerText = 'Pendente';
            badge.style.cssText = 'font-size: 0.7rem; font-weight: 700; color: #f97316; background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.25); padding: 0.15rem 0.4rem; border-radius: 4px; margin-left: 0.5rem; display: inline-block; vertical-align: middle;';
            artistEl.appendChild(badge);
        }

        // Desativa clique no card para não iniciar o jogo nesta aba
        card.style.cursor = 'default';

        const reinstallBtn = document.createElement('button');
        reinstallBtn.type = 'button';
        reinstallBtn.className = 'song-card__reinstall-btn';
        reinstallBtn.title = 'Reinstalar Música';
        reinstallBtn.innerHTML = '🔄';
        reinstallBtn.style.cssText = 'background: transparent; border: none; font-size: 1.25rem; padding: 0.25rem 0.5rem; cursor: pointer; transition: transform 0.3s ease;';
        
        reinstallBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            triggerReinstall(song.id, song.title);
        });

        reinstallBtn.addEventListener('mouseenter', () => {
            reinstallBtn.style.transform = 'rotate(180deg)';
        });
        reinstallBtn.addEventListener('mouseleave', () => {
            reinstallBtn.style.transform = 'rotate(0deg)';
        });

        const actionsDiv = document.createElement('div');
        actionsDiv.style.cssText = 'display: flex; align-items: center; gap: 0.5rem;';
        actionsDiv.appendChild(reinstallBtn);
        card.appendChild(actionsDiv);

        reinstallListEl.appendChild(frag);
    });
}

export function initSelectionTabs() {
    initTabs('selection-area', {
        onSelect: (tab) => {
            if (tab === 'reinstall') renderReinstallList(state.allSongs);
        },
    });
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
