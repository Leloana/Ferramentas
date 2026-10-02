// Editor da música: meta.json, letra LRC e "colar letra", com salvar e realinhar.
import { dom, startLoadingOverlay, stopLoadingOverlay } from '../core/dom.js';
import { showToast } from '../core/toast.js';
import { fetchSongs } from './selection-view.js';
import { openModal, closeModal } from '../ui/modal.js';
import { initTabs } from '../ui/tabs.js';

// Texto da aba "Letra" (se houver) vai para o plain_lyrics do meta.json.
// false: meta.json inválido (já avisou).
function mergePastedLyrics() {
    const metaArea = document.getElementById('editor-meta-textarea');
    const pasteArea = document.getElementById('editor-paste-lyrics-textarea');
    if (!metaArea) return true;
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
            return false;
        }
    }
    return true;
}

export function initLrcEditorModal() {
    const btnCloseEditor = document.getElementById('btn-close-editor');
    const lrcEditorForm = dom.lrcEditorForm;
    if (!btnCloseEditor) return;

    // Inicializa a navegação por abas do editor (meta / lrc / paste)
    initTabs(dom.lrcEditorModal, {
        onSelect: (tab) => {
            if (tab !== 'paste') return;
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
        },
    });

    btnCloseEditor.onclick = () => closeModal(dom.lrcEditorModal);

    const lrcArea = document.getElementById('editor-textarea');
    if (lrcArea) lrcArea.addEventListener('input', () => { lrcArea.dataset.edited = '1'; });

    const btnSaveMeta = document.getElementById('btn-save-meta');
    if (btnSaveMeta) {
        btnSaveMeta.onclick = async () => {
            const slugInput = document.getElementById('editor-slug');
            const slug = slugInput ? slugInput.value : undefined;
            const metaArea = document.getElementById('editor-meta-textarea');
            if (!slug || !metaArea) return;

            if (!mergePastedLyrics()) return;

            let metaJson;
            try {
                metaJson = JSON.parse(metaArea.value);
            } catch (e) {
                showToast("Erro de sintaxe no meta.json. Corrija antes de salvar.", "error");
                return;
            }

            // Aplica os valores dos campos editáveis da aba Meta
            const metaTitle = document.getElementById('editor-meta-title');
            const metaArtist = document.getElementById('editor-meta-artist');
            const metaLanguage = document.getElementById('editor-meta-language');
            const metaYoutube = document.getElementById('editor-meta-youtube');

            if (!metaJson.meta) metaJson.meta = {};
            if (metaTitle) metaJson.meta.title = metaTitle.value.trim();
            if (metaArtist) metaJson.meta.artist = metaArtist.value.trim();
            if (metaLanguage) metaJson.meta.language = metaLanguage.value;

            if (!metaJson.audio) metaJson.audio = {};
            if (metaYoutube) metaJson.audio.youtube_vocal_url = metaYoutube.value.trim() || null;

            metaArea.value = JSON.stringify(metaJson, null, 2);

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

        // Letra colada entra no meta.json: se ela não bate com o LRC, o servidor
        // refaz o LRC pelo áudio (a não ser que o LRC tenha sido editado à mão).
        if (!mergePastedLyrics()) return;
        const formData = new FormData(lrcEditorForm);
        const lrcArea = document.getElementById('editor-textarea');
        formData.set('lrc_edited', lrcArea && lrcArea.dataset.edited === '1' ? 'true' : 'false');
        const metaArea = document.getElementById('editor-meta-textarea');
        if (metaArea) {
            formData.set('meta_json', metaArea.value);
        }

        closeModal(dom.lrcEditorModal);
        const gen = startLoadingOverlay("Alinhando Letras...", "Mapeando sílabas das palavras e calculando fonemas...");

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
            showToast("Sincronização concluída com sucesso! Divirta-se!", "success");
            fetchSongs();
        } catch (error) {
            stopLoadingOverlay(gen);
            showToast("Erro ao salvar dados da música: " + error.message, "error");
            openModal(dom.lrcEditorModal);
        }
    };
}
