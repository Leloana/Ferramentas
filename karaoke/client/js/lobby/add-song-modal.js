// Modal "Adicionar música" em três passos: escolher o vídeo, confirmar
// título e artista (busca a letra) e revisar a letra antes de enfileirar.
import { state } from '../state.js';
import { iconSvg } from '../icons.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from '../dom.js';
import { showToast } from '../toast.js';
import { promptGenerationOptions } from '../selection-view.js';
import { openModal, closeModal } from '../modal.js';
import { initYoutubeSearch, resetYoutubeSearch, isYoutubeUrl } from '../youtube-search.js';

// --- Status de busca de letras (compartilhado entre os passos 2 e 3) ---

// Aplica cor/ícone/texto a uma caixa de status, dado o tom desejado.
function paintLyricsStatus(els, tone, icon, text) {
    if (!els.box || !els.icon || !els.text) return;
    els.box.dataset.tone = tone; // cor em .status-note[data-tone] (base.css)
    els.icon.innerHTML = iconSvg(icon);
    els.text.textContent = text;
}

// Resolve o resultado de /api/fetch-lyrics para uma classificação visual única,
// usada tanto na pré-confirmação (passo 2) quanto na revisão final (passo 3).
function describeLyricsResult(result) {
    if (result && result.pending) {
        return { tone: 'blue', icon: 'search', text: 'Letra: aguardando título' };
    }
    if (!result || !result.success) {
        return { tone: 'amber', icon: 'robot', text: 'Letra não encontrada · a IA transcreve' };
    }
    const via = (name) => `via ${name}`;
    if (result.syncedLyrics) {
        const src = result.source === 'lrclib' ? 'LRCLIB' : 'API';
        return {
            tone: 'green', icon: 'check',
            text: `Letra sincronizada ${via(src)}`,
        };
    }
    const src = result.source === 'ovh' ? 'Lyrics.ovh' : 'LRCLIB';
    return { tone: 'blue', icon: 'lyrics', text: `Letra encontrada ${via(src)}` };
}

export function initAddSongModal() {
    const addSongModal = dom.addSongModal;
    const btnOpenAddSong = document.getElementById('btn-open-add-song');
    const btnCloseAddSong = document.getElementById('btn-close-add-song');
    const addSongForm = dom.addSongForm;
    if (!btnOpenAddSong) return;


    let currentStep = 1;
    let fetchedLyrics = null;  // resultado do /api/fetch-lyrics

    const setStep = (step) => {
        currentStep = step;
        addSongForm.setAttribute('data-step', step);
        const scroller = addSongModal.querySelector('.modal-content');
        if (scroller) scroller.scrollTop = 0; // cada passo começa do topo
        const btnSubmit = document.getElementById('btn-submit-song');
        if (btnSubmit) {
            btnSubmit.innerText = (step === 3) ? 'Adicionar à fila' : 'Avançar';
        }
    };

    const step2StatusEls = {
        box: document.getElementById('lyrics-fetch-status'),
        icon: document.getElementById('lyrics-fetch-icon'),
        text: document.getElementById('lyrics-fetch-text'),
    };
    const updateLyricsStatus = (result) => {
        const { tone, icon, text } = describeLyricsResult(result);
        paintLyricsStatus(step2StatusEls, tone, icon, text);
    };

    const btnBackStep1 = document.getElementById('btn-back-step-1');
    if (btnBackStep1) {
        btnBackStep1.onclick = () => {
            if (currentStep === 2) setStep(1);
            else if (currentStep === 3) setStep(2);
        };
    }

    btnOpenAddSong.onclick = () => {
        addSongForm.reset();
        fetchedLyrics = null;
        updateLyricsStatus({ pending: true });

        const advancedOptionsContainer = document.getElementById('advanced-options-container');
        const advancedToggleIcon = document.getElementById('advanced-toggle-icon');
        const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
        if (advancedOptionsContainer) advancedOptionsContainer.removeAttribute('data-open');
        if (advancedToggleIcon) advancedToggleIcon.innerHTML = iconSvg('chevron-down');
        if (btnToggleAdvanced) btnToggleAdvanced.classList.remove('advanced-toggle--open');

        state.activeUploadTab = 'youtube';
        resetYoutubeSearch();
        setStep(1);
        openModal(addSongModal);
    };

    // Escolheu um resultado da busca (ou colou link): segue para o passo 2
    initYoutubeSearch(() => {
        const btnSubmit = document.getElementById('btn-submit-song');
        if (btnSubmit && !btnSubmit.disabled) btnSubmit.click();
    });

    const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
    const advancedOptionsContainer = document.getElementById('advanced-options-container');
    const advancedToggleIcon = document.getElementById('advanced-toggle-icon');

    if (btnToggleAdvanced && advancedOptionsContainer) {
        btnToggleAdvanced.onclick = () => {
            const willOpen = !advancedOptionsContainer.hasAttribute('data-open');
            if (willOpen) advancedOptionsContainer.setAttribute('data-open', '');
            else advancedOptionsContainer.removeAttribute('data-open');
            advancedToggleIcon.innerHTML = iconSvg(willOpen ? 'chevron-up' : 'chevron-down');
            btnToggleAdvanced.classList.toggle('advanced-toggle--open', willOpen);
        };
    }

    btnCloseAddSong.onclick = () => closeModal(addSongModal);

    // Esc / Voltar da TV / botão do navegador recuam um passo antes de fechar
    addSongModal._onBack = () => {
        if (currentStep <= 1) return false;
        document.getElementById('btn-back-step-1').click();
        return true;
    };

    // Seta de voltar do título: recua um passo; no 1º passo, fecha
    const btnAddSongBack = document.getElementById('btn-add-song-back');
    if (btnAddSongBack) {
        btnAddSongBack.onclick = () => {
            if (currentStep > 1) document.getElementById('btn-back-step-1').click();
            else closeModal(addSongModal);
        };
    }

    addSongForm.onsubmit = async (e) => {
        e.preventDefault();

        if (currentStep === 1) {
            {
                const vocalUrlInput = document.getElementById('youtube-vocal-url');
                const searchInput = document.getElementById('youtube-search-input');
                if (!vocalUrlInput.value.trim() && searchInput && isYoutubeUrl(searchInput.value.trim())) {
                    vocalUrlInput.value = searchInput.value.trim();
                }
                const vocalUrl = vocalUrlInput.value.trim();
                if (!vocalUrl) {
                    showToast("Busque a música pelo nome e escolha um dos resultados.", "error");
                    if (searchInput) searchInput.focus();
                    return;
                }
                if (!vocalUrl.includes("youtube.com") && !vocalUrl.includes("youtu.be")) {
                    showToast("Por favor, insira uma URL do YouTube válida para a música original.", "error");
                    return;
                }

                const backingUrl = document.getElementById('youtube-backing-url').value.trim();
                if (backingUrl && !backingUrl.includes("youtube.com") && !backingUrl.includes("youtu.be")) {
                    showToast("Por favor, insira uma URL do YouTube válida para o canal instrumental ou deixe em branco para gerar automaticamente com IA.", "error");
                    return;
                }

                const btnSubmit = document.getElementById('btn-submit-song');
                const origText = btnSubmit.innerText;
                btnSubmit.innerText = "Buscando dados...";
                btnSubmit.disabled = true;

                const picked = state.pickedYoutube;
                if (picked && picked.url === vocalUrl && (picked.title || picked.artist)) {
                    // A busca já trouxe artista/título sugeridos: sem nova consulta ao YouTube
                    document.getElementById('song-title').value = picked.title || '';
                    document.getElementById('song-artist').value = picked.artist || '';
                } else {
                    try {
                        const res = await fetch(`/api/youtube-metadata?url=${encodeURIComponent(vocalUrl)}`);
                        if (res.ok) {
                            const metadata = await res.json();
                            document.getElementById('song-title').value = metadata.title || '';
                            document.getElementById('song-artist').value = metadata.artist || '';
                        } else {
                            console.warn("Falha ao extrair metadados automaticamente do YouTube");
                            document.getElementById('song-title').value = '';
                            document.getElementById('song-artist').value = '';
                        }
                    } catch (err) {
                        console.error("Erro ao buscar metadados do YouTube:", err);
                        document.getElementById('song-title').value = '';
                        document.getElementById('song-artist').value = '';
                    }
                }

                // A letra será buscada APÓS o usuário confirmar/corrigir artista e título no step 2
                updateLyricsStatus({ pending: true });

                btnSubmit.innerText = origText;
                btnSubmit.disabled = false;
                setStep(2);
            }
            return;
        }

        if (currentStep === 2) {
            const songTitle = document.getElementById('song-title').value.trim();
            const songArtist = document.getElementById('song-artist').value.trim();
            if (!songTitle || !songArtist) {
                showToast("Por favor, preencha o Título da Música e o Artista / Banda.", "error");
                return;
            }

            // Busca letra automaticamente com os nomes CONFIRMADOS pelo usuário
            const btnSubmit = document.getElementById('btn-submit-song');
            const origText = btnSubmit.innerText;
            btnSubmit.innerText = "Buscando letra...";
            btnSubmit.disabled = true;

            try {
                const lyricsRes = await fetch(`/api/fetch-lyrics?artist=${encodeURIComponent(songArtist)}&track=${encodeURIComponent(songTitle)}`);
                fetchedLyrics = await lyricsRes.json();
            } catch (err) {
                console.error("Erro ao buscar letra:", err);
                fetchedLyrics = { success: false };
            }
            updateLyricsStatus(fetchedLyrics);

            btnSubmit.innerText = origText;
            btnSubmit.disabled = false;

            // Preenche Passo 3 e avança
            const step3StatusEls = {
                box: document.getElementById('lyrics-step3-status'),
                icon: document.getElementById('lyrics-step3-icon'),
                text: document.getElementById('lyrics-step3-text'),
            };
            const textarea = document.getElementById('lyrics-step3-textarea');
            if (step3StatusEls.box && textarea) {
                const { tone, icon, text } = describeLyricsResult(fetchedLyrics);
                paintLyricsStatus(step3StatusEls, tone, icon, text);
                if (!fetchedLyrics || !fetchedLyrics.success) {
                    textarea.value = '';
                } else {
                    textarea.value = fetchedLyrics.plainLyrics || '';
                }
            }

            setStep(3);
            return;
        }

        // Se chegamos no Passo 3
        const songTitle = document.getElementById('song-title').value.trim();
        const songArtist = document.getElementById('song-artist').value.trim();
        const textarea = document.getElementById('lyrics-step3-textarea');
        const confirmedPlainLyrics = textarea ? textarea.value.trim() : '';

        // Atualiza plainLyrics/syncedLyrics com base na revisão
        if (fetchedLyrics && fetchedLyrics.success) {
            if (fetchedLyrics.plainLyrics !== confirmedPlainLyrics) {
                // Se o usuário editou a letra plana, invalidamos o LRC sincronizado original
                fetchedLyrics.syncedLyrics = null;
                fetchedLyrics.plainLyrics = confirmedPlainLyrics || null;
            }
        } else if (confirmedPlainLyrics) {
            fetchedLyrics = { success: true, plainLyrics: confirmedPlainLyrics, syncedLyrics: null, source: 'user' };
        }

        // Se temos LRC sincronizado, não precisa perguntar PRO vs FLASH
        const hasSyncedLrc = fetchedLyrics && fetchedLyrics.success && fetchedLyrics.syncedLyrics;
        let alignLyrics = false;
        if (!hasSyncedLrc) {
            closeModal(addSongModal);
            const choice = await promptGenerationOptions();
            if (!choice) {
                openModal(addSongModal);
                return;
            }
            alignLyrics = (choice === 'pro');
        }

        const formData = new FormData(addSongForm);
        formData.set('title', songTitle);
        formData.set('artist', songArtist);
        formData.set('align_lyrics', alignLyrics);

        const vocalUrlInput = document.getElementById('youtube-vocal-url');
        if (vocalUrlInput && vocalUrlInput.value.trim()) {
            formData.set('youtube_url', vocalUrlInput.value.trim());
        }

        // Inclui letras (synced LRC e/ou plain lyrics)
        if (fetchedLyrics && fetchedLyrics.success) {
            if (fetchedLyrics.syncedLyrics) {
                formData.set('synced_lrc', fetchedLyrics.syncedLyrics);
            }
            if (fetchedLyrics.plainLyrics) {
                formData.set('plain_lyrics', fetchedLyrics.plainLyrics);
            }
        } else {
            formData.set('plain_lyrics', '');
        }

        const gen = startLoadingOverlay("Adicionando na Fila...", "Enfileirando música para processamento em segundo plano...");

        try {
            const response = await fetch('/api/queue/add', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Erro desconhecido");
            }

            await response.json();
            stopLoadingOverlay(gen);

            showToast("Música adicionada à fila com sucesso! O processamento rodará em segundo plano.", "success");

            closeModal(addSongModal);

            // Muda para a aba de Fila para o usuário acompanhar!
            const tabQueue = document.getElementById('tab-btn-queue');
            if (tabQueue) tabQueue.click();

        } catch (error) {
            stopLoadingOverlay(gen);
            showToast("Erro ao adicionar música: " + error.message, "error");
            openModal(addSongModal);
            setStep(3);
        }
    };
}
