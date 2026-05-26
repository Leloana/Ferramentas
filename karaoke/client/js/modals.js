import { state } from './state.js';
import { dom, startLoadingOverlay, stopLoadingOverlay } from './dom.js';
import { activeRoomId } from './config.js';
import { showToast } from './toast.js';
import { fetchSongs, loadAndOpenLrcEditor, promptGenerationOptions } from './selection-view.js';

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
    let fetchedLyrics = null;  // resultado do /api/fetch-lyrics

    const setStep = (step) => {
        currentStep = step;
        addSongForm.setAttribute('data-step', step);
        const btnSubmit = document.getElementById('btn-submit-song');
        if (btnSubmit) {
            btnSubmit.innerText = (step === 1) ? 'Avançar ➡️' : 'Confirmar e Criar 🎵';
        }
    };

    const updateLyricsStatus = (result) => {
        const statusDiv = document.getElementById('lyrics-fetch-status');
        const icon = document.getElementById('lyrics-fetch-icon');
        const text = document.getElementById('lyrics-fetch-text');
        if (!statusDiv || !icon || !text) return;

        if (result && result.pending) {
            statusDiv.style.background = 'rgba(59, 130, 246, 0.1)';
            statusDiv.style.borderColor = 'rgba(59, 130, 246, 0.3)';
            statusDiv.style.color = '#93c5fd';
            icon.textContent = '🔍';
            text.textContent = 'Confirme o artista e título acima — a letra será buscada automaticamente em seguida.';
        } else if (!result || !result.success) {
            statusDiv.style.background = 'rgba(251, 191, 36, 0.1)';
            statusDiv.style.borderColor = 'rgba(251, 191, 36, 0.3)';
            statusDiv.style.color = '#fcd34d';
            icon.textContent = '🤖';
            text.textContent = 'Nenhuma letra encontrada online — a IA vai transcrever diretamente do áudio.';
        } else if (result.syncedLyrics) {
            statusDiv.style.background = 'rgba(34, 197, 94, 0.1)';
            statusDiv.style.borderColor = 'rgba(34, 197, 94, 0.3)';
            statusDiv.style.color = '#86efac';
            icon.textContent = '✅';
            text.textContent = `Letra sincronizada encontrada via ${result.source === 'lrclib' ? 'LRCLIB' : 'API'}! O LRC será usado diretamente — não será necessário gerar.`;
        } else if (result.plainLyrics) {
            statusDiv.style.background = 'rgba(59, 130, 246, 0.1)';
            statusDiv.style.borderColor = 'rgba(59, 130, 246, 0.3)';
            statusDiv.style.color = '#93c5fd';
            icon.textContent = '📝';
            text.textContent = `Letra encontrada via ${result.source === 'ovh' ? 'Lyrics.ovh' : 'LRCLIB'}! Será usada como guia para o alinhamento automático.`;
        }
    };

    /**
     * Abre o modal de verificação de letra para o usuário revisar/editar a letra
     * antes de prosseguir com o upload. Retorna a letra confirmada ou null se cancelar.
     */
    const showLyricsReviewModal = (fetchedResult) => {
        return new Promise((resolve) => {
            const modal = document.getElementById('lyrics-review-modal');
            const textarea = document.getElementById('lyrics-review-textarea');
            const statusDiv = document.getElementById('lyrics-review-status');
            const btnConfirm = document.getElementById('btn-confirm-lyrics-review');
            const btnClose = document.getElementById('btn-close-lyrics-review');

            if (!modal || !textarea) {
                resolve(fetchedResult?.plainLyrics || null);
                return;
            }

            // Configura status
            if (statusDiv) {
                if (fetchedResult?.syncedLyrics) {
                    statusDiv.style.background = 'rgba(34, 197, 94, 0.1)';
                    statusDiv.style.border = '1px solid rgba(34, 197, 94, 0.3)';
                    statusDiv.style.color = '#86efac';
                    statusDiv.innerHTML = '✅ <strong>LRC sincronizado encontrado!</strong> Revise a letra abaixo antes de continuar.';
                } else if (fetchedResult?.plainLyrics) {
                    statusDiv.style.background = 'rgba(59, 130, 246, 0.1)';
                    statusDiv.style.border = '1px solid rgba(59, 130, 246, 0.3)';
                    statusDiv.style.color = '#93c5fd';
                    statusDiv.innerHTML = '📝 <strong>Letra encontrada.</strong> Confira se está correta e edite se necessário.';
                } else {
                    statusDiv.style.background = 'rgba(251, 191, 36, 0.1)';
                    statusDiv.style.border = '1px solid rgba(251, 191, 36, 0.3)';
                    statusDiv.style.color = '#fcd34d';
                    statusDiv.innerHTML = '⚠️ <strong>Nenhuma letra encontrada online.</strong> Cole a letra correta abaixo ou deixe em branco para a IA transcrever.';
                }
            }

            // Preenche textarea com plain lyrics (nunca LRC)
            textarea.value = fetchedResult?.plainLyrics || '';

            const cleanup = () => {
                modal.removeAttribute('data-open');
                if (btnConfirm) btnConfirm.removeEventListener('click', onConfirm);
                if (btnClose) btnClose.removeEventListener('click', onCancel);
            };

            const onConfirm = () => {
                const edited = textarea.value.trim();
                cleanup();
                resolve(edited || null);
            };

            const onCancel = () => {
                cleanup();
                resolve(null);
            };

            if (btnConfirm) btnConfirm.addEventListener('click', onConfirm);
            if (btnClose) btnClose.addEventListener('click', onCancel);

            modal.setAttribute('data-open', 'true');
        });
    };

    const btnBackStep1 = document.getElementById('btn-back-step-1');
    if (btnBackStep1) {
        btnBackStep1.onclick = () => {
            setStep(1);
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
                }

                // A letra será buscada APÓS o usuário confirmar/corrigir artista e título no step 2
                updateLyricsStatus({ pending: true });

                btnSubmit.innerText = origText;
                btnSubmit.disabled = false;
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

        // Busca letra automaticamente com os nomes CONFIRMADOS pelo usuário
        const btnSubmit = document.getElementById('btn-submit-song');
        const origText = btnSubmit.innerText;
        btnSubmit.innerText = "Buscando letra... 🔍";
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

        // Mostra modal para o usuário revisar/editar a letra (sempre plain lyrics, nunca LRC)
        const confirmedPlainLyrics = await showLyricsReviewModal(fetchedLyrics);
        if (confirmedPlainLyrics === null) {
            // Usuário cancelou — volta ao step 2
            return;
        }

        // Atualiza plainLyrics com o texto confirmado/editado pelo usuário
        if (fetchedLyrics && fetchedLyrics.success) {
            fetchedLyrics.plainLyrics = confirmedPlainLyrics || fetchedLyrics.plainLyrics;
        } else if (confirmedPlainLyrics) {
            fetchedLyrics = { success: true, plainLyrics: confirmedPlainLyrics, syncedLyrics: null, source: 'user' };
        }

        updateLyricsStatus(fetchedLyrics);

        // Se temos LRC sincronizado, não precisa perguntar PRO vs FLASH
        const hasSyncedLrc = fetchedLyrics && fetchedLyrics.success && fetchedLyrics.syncedLyrics;
        let alignLyrics = false;
        if (!hasSyncedLrc) {
            addSongModal.removeAttribute('data-open');
            const choice = await promptGenerationOptions();
            if (!choice) {
                addSongModal.setAttribute('data-open', 'true');
                return;
            }
            alignLyrics = (choice === 'pro');
        }

        const formData = new FormData(addSongForm);
        formData.set('title', songTitle);
        formData.set('artist', songArtist);
        formData.set('align_lyrics', alignLyrics);

        // Inclui letras fetched (synced LRC e/ou plain lyrics)
        if (fetchedLyrics && fetchedLyrics.success) {
            if (fetchedLyrics.syncedLyrics) {
                formData.set('synced_lrc', fetchedLyrics.syncedLyrics);
                // Não envia plain_lyrics quando tem synced — backend preserva o LRC
            } else if (fetchedLyrics.plainLyrics) {
                formData.set('plain_lyrics', fetchedLyrics.plainLyrics);
            }
        }

        const gen = state.activeUploadTab === 'youtube'
            ? startLoadingOverlay("Preparando Música...", "Baixando áudio, separando vocal e gerando rascunho do LRC... 🎧 Pode levar 1-2min.", true)
            : startLoadingOverlay("Processando Áudio...", "Separando vocal e gerando rascunho do LRC... 🎧 Pode levar 1-2min.", true);

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
            stopLoadingOverlay(gen);

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
            stopLoadingOverlay(gen);
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
        if (dom.lrcEditorModal) {
            dom.lrcEditorModal.setAttribute('data-editor-tab', tabName);
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

    btnCloseEditor.onclick = () => {
        dom.lrcEditorModal.removeAttribute('data-open');
    };

    const btnSaveMeta = document.getElementById('btn-save-meta');
    if (btnSaveMeta) {
        btnSaveMeta.onclick = async () => {
            const slug = document.getElementById('editor-slug')?.value;
            const metaArea = document.getElementById('editor-meta-textarea');
            const pasteArea = document.getElementById('editor-paste-lyrics-textarea');
            if (!slug || !metaArea) return;

            // Se há texto na aba "Letra", formata e injeta no meta.json antes de salvar
            if (pasteArea && pasteArea.value.trim()) {
                const rawLyrics = pasteArea.value;
                const normalized = rawLyrics.replace(/\r\n/g, '\n');
                const lines = normalized.split('\n');

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

                try {
                    const metaJsonStr = metaArea.value.trim() || '{}';
                    const meta = JSON.parse(metaJsonStr);
                    if (!meta.lyrics) {
                        meta.lyrics = {};
                    }
                    meta.lyrics.plain_lyrics = formattedLyrics;
                    metaArea.value = JSON.stringify(meta, null, 2);
                    pasteArea.value = '';
                } catch (e) {
                    showToast("Erro ao ler o meta.json. Certifique-se de que ele é um JSON válido.", "error");
                    return;
                }
            }

            let metaJson;
            try {
                metaJson = JSON.parse(metaArea.value);
            } catch (e) {
                showToast("Erro de sintaxe no meta.json. Corrija antes de salvar.", "error");
                return;
            }

            btnSaveMeta.disabled = true;
            const origText = btnSaveMeta.innerText;
            btnSaveMeta.innerText = "Salvando...";

            try {
                const formData = new FormData();
                formData.set('slug', slug);
                formData.set('meta_json', metaArea.value);

                const response = await fetch('/api/save-meta', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || "Erro ao salvar");
                }

                const data = await response.json();
                if (data.slug) {
                    const slugInput = document.getElementById('editor-slug');
                    if (slugInput) slugInput.value = data.slug;
                }

                showToast("Meta salvo com sucesso!", "success");
            } catch (error) {
                showToast("Erro ao salvar meta: " + error.message, "error");
            } finally {
                btnSaveMeta.disabled = false;
                btnSaveMeta.innerText = origText;
            }
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
        const gen = startLoadingOverlay("Alinhando Letras...", "Mapeando sílabas das palavras e calculando fonemas... 📝⚡");

        try {
            const response = await fetch('/api/save-lyrics', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Erro ao salvar");
            }

            stopLoadingOverlay(gen);
            showToast("Sincronização concluída com sucesso! Divirta-se! 🎉", "success");
            fetchSongs();
        } catch (error) {
            stopLoadingOverlay(gen);
            showToast("Erro ao salvar dados da música: " + error.message, "error");
            dom.lrcEditorModal.setAttribute('data-open', 'true');
        }
    };
}
