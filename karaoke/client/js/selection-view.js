import { state } from './state.js';
import { dom } from './dom.js';
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
        state.allSongs = songs;

        document.getElementById('search-input').value = '';
        renderSongs(songs);
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

    const tpl = document.getElementById('song-card-tpl');
    songsList.forEach(song => {
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
    dom.audioPlayer.src = `/songs/${song.id}/audio`;

    const savedVolume = localStorage.getItem('karaoke_backing_volume');
    if (savedVolume !== null) {
        dom.audioPlayer.volume = parseFloat(savedVolume);
    }
}

export async function loadAndOpenLrcEditor(slug) {
    dom.loadingStatusTitle.innerText = "Carregando Letras...";
    dom.loadingStatusDesc.innerText = "Buscando o arquivo LRC no servidor...";
    dom.loadingOverlay.style.display = 'flex';

    try {
        const resp = await fetch(`/api/get-lyrics?slug=${encodeURIComponent(slug)}&t=${Date.now()}`, {
            headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });
        if (!resp.ok) throw new Error("Não foi possível carregar as letras");
        const data = await resp.json();

        dom.loadingOverlay.style.display = 'none';

        if (data.success) {
            document.getElementById('editor-slug').value = slug;
            document.getElementById('editor-language').value = data.language;
            document.getElementById('editor-textarea').value = data.lyrics;
            dom.lrcEditorModal.style.display = 'flex';
        } else {
            showToast("Erro: O arquivo de letras não foi localizado no servidor.", "error");
        }
    } catch (e) {
        dom.loadingOverlay.style.display = 'none';
        showToast("Erro ao carregar as letras: " + e.message, "error");
    }
}

export function initSearch() {
    const input = document.getElementById('search-input');
    if (!input) return;
    input.oninput = (e) => {
        const query = e.target.value.toLowerCase().trim();
        const filtered = state.allSongs.filter(song =>
            song.title.toLowerCase().includes(query) ||
            (song.artist && song.artist.toLowerCase().includes(query))
        );
        renderSongs(filtered);
    };
}
