import { state } from './state.js';
import { dom } from './dom.js';
import { activeRoomId } from './config.js';
import { showToast } from './toast.js';
import { fetchSongs } from './selection-view.js';

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

    btnOpenAddSong.onclick = () => {
        addSongForm.reset();

        const advancedOptionsContainer = document.getElementById('advanced-options-container');
        const advancedToggleIcon = document.getElementById('advanced-toggle-icon');
        const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
        if (advancedOptionsContainer) advancedOptionsContainer.style.display = 'none';
        if (advancedToggleIcon) advancedToggleIcon.innerText = '▼';
        if (btnToggleAdvanced) btnToggleAdvanced.classList.remove('advanced-toggle--open');

        setTab('youtube');
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

        if (state.activeUploadTab === 'local') {
            const vocalFile = document.getElementById('vocal-file').files[0];
            const backingFile = document.getElementById('backing-file').files[0];
            if (!vocalFile || !backingFile) {
                showToast("Por favor, selecione os arquivos Vocal e Instrumental locais.", "error");
                return;
            }
        } else if (state.activeUploadTab === 'youtube') {
            const vocalUrl = document.getElementById('youtube-vocal-url').value.trim();
            const backingUrl = document.getElementById('youtube-backing-url').value.trim();
            if (!vocalUrl || !backingUrl) {
                showToast("Por favor, insira ambos os links do YouTube (Vocal e Instrumental).", "error");
                return;
            }
            if ((!vocalUrl.includes("youtube.com") && !vocalUrl.includes("youtu.be")) ||
                (!backingUrl.includes("youtube.com") && !backingUrl.includes("youtu.be"))) {
                showToast("Por favor, insira URLs do YouTube válidas para ambos os campos.", "error");
                return;
            }
        }

        const formData = new FormData(addSongForm);
        addSongModal.style.display = 'none';
        if (state.activeUploadTab === 'youtube') {
            dom.loadingStatusTitle.innerText = "Baixando do YouTube...";
            dom.loadingStatusDesc.innerText = "Baixando as pistas Vocal e Instrumental em paralelo...";
        } else {
            dom.loadingStatusTitle.innerText = "Cortando Áudios...";
            dom.loadingStatusDesc.innerText = "Fatiando os vocais e instrumental com pydub...";
        }
        dom.loadingOverlay.style.display = 'flex';

        try {
            const lrcFile = document.getElementById('lrc-file').files[0];
            if (!lrcFile) {
                setTimeout(() => {
                    dom.loadingStatusTitle.innerText = "IA Transcrevendo Letra...";
                    if (state.activeUploadTab === 'youtube') {
                        dom.loadingStatusDesc.innerText = "Aguardando o Whisper extrair a letra do áudio baixado...";
                    } else {
                        dom.loadingStatusDesc.innerText = "Isso pode levar alguns segundos na GPU RTX 4070...";
                    }
                }, 4000);
            }

            const response = await fetch('/api/upload-song', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Erro desconhecido");
            }

            const data = await response.json();
            dom.loadingOverlay.style.display = 'none';

            if (data.lyrics_status === 'draft') {
                document.getElementById('editor-slug').value = data.slug;
                document.getElementById('editor-language').value = formData.get('language');
                document.getElementById('editor-textarea').value = data.draft_lrc;
                dom.lrcEditorModal.style.display = 'flex';
            } else {
                if (data.fallback_used) {
                    showToast("Música adicionada! Nota: A IA teve baixa correspondência e ativou a distribuição uniforme. Recomendamos ajustar manualmente os tempos no Sincronizador para um resultado perfeito!", "warning");
                } else {
                    showToast("Música adicionada com sucesso! Divirta-se! 🎉", "success");
                }
                fetchSongs();
            }
        } catch (error) {
            dom.loadingOverlay.style.display = 'none';
            showToast("Erro ao adicionar música: " + error.message, "error");
            addSongModal.style.display = 'flex';
        }
    };
}

function initLrcEditorModal() {
    const btnCloseEditor = document.getElementById('btn-close-editor');
    const lrcEditorForm = dom.lrcEditorForm;
    if (!btnCloseEditor) return;

    btnCloseEditor.onclick = () => {
        dom.lrcEditorModal.style.display = 'none';
    };

    lrcEditorForm.onsubmit = async (e) => {
        e.preventDefault();
        const formData = new FormData(lrcEditorForm);

        dom.lrcEditorModal.style.display = 'none';
        dom.loadingStatusTitle.innerText = "Alinhando Letras...";
        dom.loadingStatusDesc.innerText = "Mapeando sílabas das palavras e calculando fonemas...";
        dom.loadingOverlay.style.display = 'flex';

        try {
            const response = await fetch('/api/save-lyrics', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Erro ao salvar");
            }

            dom.loadingOverlay.style.display = 'none';
            showToast("Sincronização concluída com sucesso! Divirta-se! 🎉", "success");
            fetchSongs();
        } catch (error) {
            dom.loadingOverlay.style.display = 'none';
            showToast("Erro ao salvar letras: " + error.message, "error");
            dom.lrcEditorModal.style.display = 'flex';
        }
    };
}
