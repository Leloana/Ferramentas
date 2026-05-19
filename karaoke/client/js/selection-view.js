import { state } from './state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from './dom.js';
import { showToast } from './toast.js';

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
        renderSongs(songs);
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

export function renderSongs(songsList) {
    dom.songListEl.innerHTML = '';

    const readySongs = songsList.filter(song => song.is_ready !== false);

    if (readySongs.length === 0) {
        dom.songListEl.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--dim)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>
                <h4>Nenhuma música encontrada</h4>
                <p>Tente buscar por outro termo ou adicione arquivos na pasta <code>server/songs/</code>!</p>
            </div>
        `;
        return;
    }

    const tpl = document.getElementById('song-card-tpl');
    readySongs.forEach(song => {
        const frag = tpl.content.cloneNode(true);
        const card = frag.querySelector('.song-card');
        const titleEl = frag.querySelector('.song-card__title');
        const artistEl = frag.querySelector('.song-card__artist');
        const editBtn = frag.querySelector('.song-card__edit-btn');
        const deleteBtn = frag.querySelector('.song-card__delete-btn');

        titleEl.innerText = song.title;
        artistEl.innerText = song.artist || "Artista Desconhecido";

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

        dom.songListEl.appendChild(frag);
    });
}

export function selectSong(song) {
    state.selectedSongId = song.id;
    document.getElementById('current-song-title').innerText = song.title;
    dom.selectionArea.style.display = 'none';
    dom.gameArea.style.display = 'block';
    document.getElementById('sync-controls').style.display = 'flex';
    dom.audioPlayer.src = `/songs/${song.id}/audio`;

    const savedVolume = localStorage.getItem('karaoke_backing_volume');
    if (savedVolume !== null) {
        dom.audioPlayer.volume = parseFloat(savedVolume);
    }
}

export async function loadAndOpenLrcEditor(slug) {
    startLoadingOverlay("Carregando Letras...", "Buscando informações no servidor...");

    try {
        const resp = await fetch(`/api/get-lyrics?slug=${encodeURIComponent(slug)}&t=${Date.now()}`, {
            headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });
        if (!resp.ok) throw new Error("Não foi possível carregar os dados");
        const data = await resp.json();

        stopLoadingOverlay();

        if (data.success) {
            document.getElementById('editor-slug').value = slug;
            document.getElementById('editor-language').value = data.language;
            document.getElementById('editor-textarea').value = data.lyrics || '';

            const metaArea = document.getElementById('editor-meta-textarea');
            if (metaArea) {
                metaArea.value = data.meta_json || '';
            }

            // Ativa aba meta por padrão ao abrir
            const sectionMeta = document.getElementById('editor-section-meta');
            const sectionLrc = document.getElementById('editor-section-lrc');
            const btnTabMeta = document.getElementById('btn-tab-meta');
            const btnTabLrc = document.getElementById('btn-tab-lrc');

            if (sectionMeta) sectionMeta.style.display = 'block';
            if (sectionLrc) sectionLrc.style.display = 'none';
            if (btnTabMeta) {
                btnTabMeta.style.background = 'var(--accent)';
                btnTabMeta.style.color = '#000';
            }
            if (btnTabLrc) {
                btnTabLrc.style.background = 'transparent';
                btnTabLrc.style.color = 'var(--dim)';
            }

            dom.lrcEditorModal.style.display = 'flex';
        } else {
            showToast("Erro: Os arquivos da música não foram localizados no servidor.", "error");
        }
    } catch (e) {
        stopLoadingOverlay();
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
        renderSongs(filtered);
    };

    initSelectionTabs();
}

export async function triggerReinstall(songId, songTitle) {
    const confirmed = confirm(`Tem certeza que deseja reinstalar a música "${songTitle || songId}"?\n\nIsso apagará os áudios e letras atuais, gerando tudo do zero a partir do "meta.json" original.`);
    if (!confirmed) return;

    if (dom.lrcEditorModal) dom.lrcEditorModal.style.display = 'none';

    startLoadingOverlay("Reinstalando...", "Executando processo de download, separação Demucs (GPU) e alinhamento Whisper... 🔄🎧", true);

    try {
        const response = await fetch(`/api/reinstall-song/${songId}`, {
            method: 'POST'
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Erro ao reinstalar");
        }

        const data = await response.json();
        stopLoadingOverlay();
        showToast(data.message || "Música reinstalada com sucesso!", "success");
        if (typeof fetchSongs === 'function') fetchSongs();

    } catch (error) {
        stopLoadingOverlay();
        showToast("Erro ao reinstalar: " + error.message, "error");
        if (dom.lrcEditorModal && document.getElementById('editor-slug')?.value === songId) {
            dom.lrcEditorModal.style.display = 'flex';
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
    const tabSongs = document.getElementById('tab-btn-songs');
    const tabReinstall = document.getElementById('tab-btn-reinstall');
    const songsContent = document.getElementById('songs-tab-content');
    const reinstallContent = document.getElementById('reinstall-tab-content');

    if (!tabSongs || !tabReinstall || !songsContent || !reinstallContent) return;

    tabSongs.onclick = () => {
        tabSongs.className = 'tab-btn tab-btn--active';
        tabSongs.style.background = 'var(--accent-gradient)';
        tabSongs.style.color = '#000';
        tabSongs.style.fontWeight = '800';
        
        tabReinstall.className = 'tab-btn tab-btn--inactive';
        tabReinstall.style.background = 'transparent';
        tabReinstall.style.color = 'var(--dim)';
        tabReinstall.style.fontWeight = '700';

        songsContent.style.display = 'block';
        reinstallContent.style.display = 'none';
    };

    tabReinstall.onclick = () => {
        tabReinstall.className = 'tab-btn tab-btn--active';
        tabReinstall.style.background = 'var(--accent-gradient)';
        tabReinstall.style.color = '#000';
        tabReinstall.style.fontWeight = '800';
        
        tabSongs.className = 'tab-btn tab-btn--inactive';
        tabSongs.style.background = 'transparent';
        tabSongs.style.color = 'var(--dim)';
        tabSongs.style.fontWeight = '700';

        songsContent.style.display = 'none';
        reinstallContent.style.display = 'block';
        
        renderReinstallList(state.allSongs);
    };
}
