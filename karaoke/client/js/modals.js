import { state } from './state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from './dom.js';
import { activeRoomId } from './config.js';
import { showToast } from './toast.js';
import { fetchSongs, loadAndOpenLrcEditor, triggerReinstall, promptGenerationOptions } from './selection-view.js';

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
        pairingModal.setAttribute('data-open', 'true');
        pairingModal.setAttribute('data-qrcode-status', 'loading');

        // Reset pairing status and dot indicator
        const pairingStatusText = document.getElementById('pairing-status-text');
        const statusBox = document.getElementById('pairing-status-box');
        if (pairingStatusText) {
            pairingStatusText.innerText = "Aguardando conexão do celular...";
        }
        if (statusBox) {
            statusBox.removeAttribute('data-status');
        }

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
            pairingModal.setAttribute('data-qrcode-status', 'ready');
        };
    };

    btnClosePairing.onclick = () => {
        pairingModal.removeAttribute('data-open');
    };

    // Abre o modal de pareamento ao clicar no QR Code ao lado de qualquer slot de jogador
    document.querySelectorAll('.btn-qr-pairing').forEach(btn => {
        btn.onclick = () => {
            btnOpenPairing.click();
        };
    });
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
        addSongForm.setAttribute('data-upload-tab', which);
    };

    tabBtnLocal.onclick = () => setTab('local');
    tabBtnYoutube.onclick = () => setTab('youtube');

    let currentStep = 1;

    const setStep = (step) => {
        currentStep = step;
        addSongForm.setAttribute('data-step', step);
        const btnSubmit = document.getElementById('btn-submit-song');
        if (btnSubmit) {
            btnSubmit.innerText = (step === 1) ? 'Avançar ➡️' : 'Confirmar e Criar 🎵';
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
        if (advancedOptionsContainer) advancedOptionsContainer.removeAttribute('data-open');
        if (advancedToggleIcon) advancedToggleIcon.innerText = '▼';
        if (btnToggleAdvanced) btnToggleAdvanced.classList.remove('advanced-toggle--open');

        setTab('youtube');
        setStep(1);
        addSongModal.setAttribute('data-open', 'true');
    };

    const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
    const advancedOptionsContainer = document.getElementById('advanced-options-container');
    const advancedToggleIcon = document.getElementById('advanced-toggle-icon');

    if (btnToggleAdvanced && advancedOptionsContainer) {
        btnToggleAdvanced.onclick = () => {
            if (!advancedOptionsContainer.hasAttribute('data-open')) {
                advancedOptionsContainer.setAttribute('data-open', 'true');
                advancedToggleIcon.innerText = '▲';
                btnToggleAdvanced.classList.add('advanced-toggle--open');
            } else {
                advancedOptionsContainer.removeAttribute('data-open');
                advancedToggleIcon.innerText = '▼';
                btnToggleAdvanced.classList.remove('advanced-toggle--open');
            }
        };
    }
    btnCloseAddSong.onclick = () => {
        addSongModal.removeAttribute('data-open');
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

        // Prompt the user for the generation options (PRO vs Flash vs Cancel)
        addSongModal.removeAttribute('data-open');
        const choice = await promptGenerationOptions();
        if (!choice) {
            // Cancelled, show addSongModal again
            addSongModal.setAttribute('data-open', 'true');
            return;
        }

        const alignLyrics = (choice === 'pro');

        const formData = new FormData(addSongForm);
        formData.set('title', songTitle);
        formData.set('artist', songArtist);
        formData.set('align_lyrics', alignLyrics);

        if (state.activeUploadTab === 'youtube') {
            startLoadingOverlay("Preparando Música...", "Baixando áudio, separando vocal e gerando rascunho do LRC... 🎧 Pode levar 1-2min.", true);
        } else {
            startLoadingOverlay("Processando Áudio...", "Separando vocal e gerando rascunho do LRC... 🎧 Pode levar 1-2min.", true);
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

            // O backend sempre devolve um rascunho de LRC para o usuário aprovar
            // antes de finalizar a música. O `segments.json` só é gerado quando
            // o usuário salva o LRC editado (via /api/save-lyrics).
            if (data.orphan_lines && data.orphan_lines > 0) {
                showToast(`Rascunho gerado com ${data.orphan_lines} linha(s) marcadas [??:??.??] — ajuste os tempos manualmente no editor antes de salvar.`, "warning");
            } else {
                showToast("Rascunho de LRC pronto! Revise e clique em Salvar para finalizar.", "info");
            }
            loadAndOpenLrcEditor(data.slug);
        } catch (error) {
            stopLoadingOverlay();
            showToast("Erro ao adicionar música: " + error.message, "error");
            addSongModal.setAttribute('data-open', 'true');
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
    const btnTabPaste = document.getElementById('btn-tab-paste-lyrics');
    const sectionMeta = document.getElementById('editor-section-meta');
    const sectionLrc = document.getElementById('editor-section-lrc');
    const sectionPaste = document.getElementById('editor-section-paste-lyrics');

    const switchTab = (tabName) => {
        if (lrcEditorForm) {
            lrcEditorForm.setAttribute('data-editor-tab', tabName);
        }
        if (tabName === 'paste') {
            // Popula com o plain_lyrics atual do meta.json se houver
            try {
                const metaArea = document.getElementById('editor-meta-textarea');
                const pasteArea = document.getElementById('editor-paste-lyrics-textarea');
                if (metaArea && pasteArea) {
                    const meta = JSON.parse(metaArea.value);
                    if (meta && meta.lyrics && meta.lyrics.plain_lyrics) {
                        pasteArea.value = meta.lyrics.plain_lyrics;
                    }
                }
            } catch (e) {
                // Ignore se o JSON for inválido no momento
            }
        }
    };

    if (btnTabMeta && btnTabLrc && btnTabPaste) {
        btnTabMeta.onclick = () => switchTab('meta');
        btnTabLrc.onclick = () => switchTab('lrc');
        btnTabPaste.onclick = () => switchTab('paste');
    }

    const btnFormatPaste = document.getElementById('btn-format-paste-lyrics');
    if (btnFormatPaste) {
        btnFormatPaste.onclick = () => {
            const pasteArea = document.getElementById('editor-paste-lyrics-textarea');
            const metaArea = document.getElementById('editor-meta-textarea');
            if (!pasteArea || !metaArea) return;

            const rawLyrics = pasteArea.value;
            if (!rawLyrics.trim()) {
                showToast("Por favor, cole a letra da música antes de formatar.", "warning");
                return;
            }

            // Normalização: substituir \r\n por \n
            const normalized = rawLyrics.replace(/\r\n/g, '\n');
            const lines = normalized.split('\n');

            // Limpa espaços no início/fim de cada linha e colapsa linhas em branco consecutivas
            const cleanedLines = [];
            let consecutiveEmptyCount = 0;
            for (let line of lines) {
                const trimmed = line.trim();
                if (trimmed === '') {
                    consecutiveEmptyCount++;
                    if (consecutiveEmptyCount === 1) {
                        cleanedLines.push('');
                    }
                } else {
                    consecutiveEmptyCount = 0;
                    cleanedLines.push(trimmed);
                }
            }

            // Remove linhas em branco no início e no fim
            let startIndex = 0;
            while (startIndex < cleanedLines.length && cleanedLines[startIndex] === '') {
                startIndex++;
            }
            let endIndex = cleanedLines.length - 1;
            while (endIndex >= startIndex && cleanedLines[endIndex] === '') {
                endIndex--;
            }

            const finalLines = cleanedLines.slice(startIndex, endIndex + 1);
            const formattedLyrics = finalLines.join('\n');

            // Atualiza o JSON do meta.json
            try {
                const metaJsonStr = metaArea.value.trim() || '{}';
                const meta = JSON.parse(metaJsonStr);
                
                if (!meta.lyrics) {
                    meta.lyrics = {};
                }
                meta.lyrics.plain_lyrics = formattedLyrics;

                metaArea.value = JSON.stringify(meta, null, 2);
                showToast("Letra formatada e inserida no meta.json com sucesso! 🎉", "success");
                
                // Volta para a aba de Ajustes (meta.json)
                switchTab('meta');
            } catch (e) {
                console.error("Erro ao analisar meta.json:", e);
                showToast("Erro ao ler o meta.json. Certifique-se de que ele é um JSON válido antes de formatar a letra.", "error");
            }
        };
    }

    btnCloseEditor.onclick = () => {
        dom.lrcEditorModal.removeAttribute('data-open');
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

        dom.lrcEditorModal.removeAttribute('data-open');
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
            dom.lrcEditorModal.setAttribute('data-open', 'true');
        }
    };
}
