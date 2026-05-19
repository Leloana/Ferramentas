import { state } from './state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from './dom.js';
import { activeRoomId } from './config.js';
import { showToast } from './toast.js';
import { fetchSongs, loadAndOpenLrcEditor, triggerReinstall } from './selection-view.js';

export function initModals() {
    initPairingModal();
    initAddSongModal();
    initLrcEditorModal();
}

function initPairingModal() {
    const pairingModal = document.getElementById('pairing-modal');
    const btnOpenPairing = document.getElementById('btn-open-pairing');
    const btnClosePairing = document.getElementById('btn-close-pairing');
    const pairingQrcode = document.getElementById('pairing-qrcode');
    const pairingQrcodeLoading = document.getElementById('pairing-qrcode-loading');
    const pairingLink = document.getElementById('pairing-link');

    if (!btnOpenPairing) return;

    btnOpenPairing.onclick = async () => {
        pairingModal.style.display = 'flex';
        pairingQrcode.style.display = 'none';
        pairingQrcodeLoading.style.display = 'flex';

        let targetHost = window.location.host;
        try {
            const ipRes = await fetch('/api/get-ip');
            if (ipRes.ok) {
                const ipData = await ipRes.json();
                if (ipData.ip && ipData.ip !== '127.0.0.1') {
                    const port = window.location.port ? `:${window.location.port}` : '';
                    targetHost = `${ipData.ip}${port}`;
                }
            }
        } catch (e) {
            console.warn("Nao foi possivel obter o IP da rede local, usando fallback do host do navegador:", e);
        }

        const pairingUrl = `${window.location.protocol}//${targetHost}/?role=mic&room=${activeRoomId}`;
        pairingLink.href = pairingUrl;
        pairingLink.innerText = pairingUrl;

        pairingQrcode.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(pairingUrl)}`;

        pairingQrcode.onload = () => {
            pairingQrcodeLoading.style.display = 'none';
            pairingQrcode.style.display = 'block';
        };
    };

    btnClosePairing.onclick = () => {
        pairingModal.style.display = 'none';
    };
}

function initAddSongModal() {
    const addSongModal = dom.addSongModal;
    const btnOpenAddSong = document.getElementById('btn-open-add-song');
    const btnCloseAddSong = document.getElementById('btn-close-add-song');
    const addSongForm = dom.addSongForm;
    if (!btnOpenAddSong) return;

    const tabBtnLocal = document.getElementById('tab-btn-local');
    const tabBtnYoutube = document.getElementById('tab-btn-youtube');
    const sectionLocalUpload = document.getElementById('section-local-upload');
    const sectionYoutubeImport = document.getElementById('section-youtube-import');

    const setTab = (which) => {
        state.activeUploadTab = which;
        if (which === 'local') {
            tabBtnLocal.classList.add('tab-btn--active');
            tabBtnLocal.classList.remove('tab-btn--inactive');
            tabBtnYoutube.classList.remove('tab-btn--active');
            tabBtnYoutube.classList.add('tab-btn--inactive');
            sectionLocalUpload.style.display = 'block';
            sectionYoutubeImport.style.display = 'none';
        } else {
            tabBtnYoutube.classList.add('tab-btn--active');
            tabBtnYoutube.classList.remove('tab-btn--inactive');
            tabBtnLocal.classList.remove('tab-btn--active');
            tabBtnLocal.classList.add('tab-btn--inactive');
            sectionLocalUpload.style.display = 'none';
            sectionYoutubeImport.style.display = 'block';
        }
    };

    tabBtnLocal.onclick = () => setTab('local');
    tabBtnYoutube.onclick = () => setTab('youtube');

    let currentStep = 1;

    const setStep = (step) => {
        currentStep = step;
        const step1 = document.getElementById('upload-step-1');
        const step2 = document.getElementById('upload-step-2');
        const btnBack = document.getElementById('btn-back-step-1');
        const btnSubmit = document.getElementById('btn-submit-song');

        if (step === 1) {
            step1.style.display = 'block';
            step2.style.display = 'none';
            btnBack.style.display = 'none';
            btnSubmit.innerText = 'Avançar ➡️';
        } else {
            step1.style.display = 'none';
            step2.style.display = 'block';
            btnBack.style.display = 'inline-block';
            btnSubmit.innerText = 'Confirmar e Criar 🎵';
        }
    };

    const btnBackStep1 = document.getElementById('btn-back-step-1');
    if (btnBackStep1) {
        btnBackStep1.onclick = () => {
            setStep(1);
        };
    }

    btnOpenAddSong.onclick = () => {
        addSongForm.reset();

        const advancedOptionsContainer = document.getElementById('advanced-options-container');
        const advancedToggleIcon = document.getElementById('advanced-toggle-icon');
        const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
        if (advancedOptionsContainer) advancedOptionsContainer.style.display = 'none';
        if (advancedToggleIcon) advancedToggleIcon.innerText = '▼';
        if (btnToggleAdvanced) btnToggleAdvanced.classList.remove('advanced-toggle--open');

        setTab('youtube');
        setStep(1);
        addSongModal.style.display = 'flex';
    };

    const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
    const advancedOptionsContainer = document.getElementById('advanced-options-container');
    const advancedToggleIcon = document.getElementById('advanced-toggle-icon');

    if (btnToggleAdvanced && advancedOptionsContainer) {
        btnToggleAdvanced.onclick = () => {
            if (advancedOptionsContainer.style.display === 'none') {
                advancedOptionsContainer.style.display = 'block';
                advancedToggleIcon.innerText = '▲';
                btnToggleAdvanced.classList.add('advanced-toggle--open');
            } else {
                advancedOptionsContainer.style.display = 'none';
                advancedToggleIcon.innerText = '▼';
                btnToggleAdvanced.classList.remove('advanced-toggle--open');
            }
        };
    }

    document.getElementById('vocal-start').oninput = (e) => {
        document.getElementById('lyrics-start').value = e.target.value;
    };

    btnCloseAddSong.onclick = () => {
        addSongModal.style.display = 'none';
    };

    addSongForm.onsubmit = async (e) => {
        e.preventDefault();

        if (currentStep === 1) {
            if (state.activeUploadTab === 'local') {
                const vocalFile = document.getElementById('vocal-file').files[0];
                if (!vocalFile) {
                    showToast("Por favor, selecione o arquivo de áudio Vocal / Original local.", "error");
                    return;
                }
                document.getElementById('song-title').value = '';
                document.getElementById('song-artist').value = '';
                setStep(2);
            } else if (state.activeUploadTab === 'youtube') {
                const vocalUrl = document.getElementById('youtube-vocal-url').value.trim();
                if (!vocalUrl) {
                    showToast("Por favor, insira o link do YouTube da música original.", "error");
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
                btnSubmit.innerText = "Buscando dados... ⏳";
                btnSubmit.disabled = true;

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
                } finally {
                    btnSubmit.innerText = origText;
                    btnSubmit.disabled = false;
                }

                setStep(2);
            }
            return;
        }

        const songTitle = document.getElementById('song-title').value.trim();
        const songArtist = document.getElementById('song-artist').value.trim();
        if (!songTitle || !songArtist) {
            showToast("Por favor, preencha o Título da Música e o Artista / Banda.", "error");
            return;
        }

        const formData = new FormData(addSongForm);
        formData.set('title', songTitle);
        formData.set('artist', songArtist);
        addSongModal.style.display = 'none';
        if (state.activeUploadTab === 'youtube') {
            startLoadingOverlay("Preparando Música...", "Iniciando download do vocal do YouTube... 🎧", true);
        } else {
            startLoadingOverlay("Processando Áudio...", "Lendo e fatiando faixa vocal local... 🎧", true);
        }

        try {
            const response = await fetch('/api/upload-song', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Erro desconhecido");
            }

            const data = await response.json();
            stopLoadingOverlay();

            if (data.lyrics_status === 'draft') {
                loadAndOpenLrcEditor(data.slug);
            } else {
                if (data.fallback_used) {
                    showToast("Música adicionada! Nota: A IA teve baixa correspondência e ativou a distribuição uniforme. Recomendamos ajustar manualmente os tempos no Sincronizador para um resultado perfeito!", "warning");
                } else {
                    showToast("Música adicionada com sucesso! Divirta-se! 🎉", "success");
                }
                fetchSongs();
            }
        } catch (error) {
            stopLoadingOverlay();
            showToast("Erro ao adicionar música: " + error.message, "error");
            addSongModal.style.display = 'flex';
            setStep(2);
        }
    };
}

function initLrcEditorModal() {
    const btnCloseEditor = document.getElementById('btn-close-editor');
    const lrcEditorForm = dom.lrcEditorForm;
    if (!btnCloseEditor) return;

    // Inicializa a navegação por abas do editor
    const btnTabMeta = document.getElementById('btn-tab-meta');
    const btnTabLrc = document.getElementById('btn-tab-lrc');
    const sectionMeta = document.getElementById('editor-section-meta');
    const sectionLrc = document.getElementById('editor-section-lrc');

    if (btnTabMeta && btnTabLrc && sectionMeta && sectionLrc) {
        btnTabMeta.onclick = () => {
            sectionMeta.style.display = 'block';
            sectionLrc.style.display = 'none';
            btnTabMeta.style.background = 'var(--accent)';
            btnTabMeta.style.color = '#000';
            btnTabLrc.style.background = 'transparent';
            btnTabLrc.style.color = 'var(--dim)';
        };

        btnTabLrc.onclick = () => {
            sectionMeta.style.display = 'none';
            sectionLrc.style.display = 'block';
            btnTabMeta.style.background = 'transparent';
            btnTabMeta.style.color = 'var(--dim)';
            btnTabLrc.style.background = 'var(--accent)';
            btnTabLrc.style.color = '#000';
        };
    }

    btnCloseEditor.onclick = () => {
        dom.lrcEditorModal.style.display = 'none';
    };

    const btnReinstallSong = document.getElementById('btn-reinstall-song');
    if (btnReinstallSong) {
        btnReinstallSong.onclick = async () => {
            const songId = document.getElementById('editor-slug')?.value;
            const songTitle = document.getElementById('editor-meta-textarea') ? 
                (() => {
                    try {
                        const meta = JSON.parse(document.getElementById('editor-meta-textarea').value);
                        return meta.title;
                    } catch(e) { return null; }
                })() : null;
            if (!songId) return;
            await triggerReinstall(songId, songTitle || songId);
        };
    }

    lrcEditorForm.onsubmit = async (e) => {
        e.preventDefault();
        
        // Garante que o meta.json e o lyrics_lrc sejam enviados no FormData
        const formData = new FormData(lrcEditorForm);
        const metaArea = document.getElementById('editor-meta-textarea');
        if (metaArea) {
            formData.set('meta_json', metaArea.value);
        }

        dom.lrcEditorModal.style.display = 'none';
        startLoadingOverlay("Alinhando Letras...", "Mapeando sílabas das palavras e calculando fonemas... 📝⚡");

        try {
            const response = await fetch('/api/save-lyrics', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Erro ao salvar");
            }

            stopLoadingOverlay();
            showToast("Sincronização concluída com sucesso! Divirta-se! 🎉", "success");
            fetchSongs();
        } catch (error) {
            stopLoadingOverlay();
            showToast("Erro ao salvar dados da música: " + error.message, "error");
            dom.lrcEditorModal.style.display = 'flex';
        }
    };
}
