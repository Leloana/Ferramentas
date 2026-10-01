// Modais da biblioteca de músicas na TV.
import { urlParams } from '../config.js';
import { initPairingModal } from './pairing-modal.js';
import { initAddSongModal } from './add-song-modal.js';
import { initLrcEditorModal } from './lrc-editor-modal.js';

export function initModals() {
    initPairingModal();
    initAddSongModal();
    initLrcEditorModal();

    // Auto-open add-song modal when URL contains ?open=add-song (QR code scan)
    if (urlParams.get('open') === 'add-song') {
        const btnOpenAddSong = document.getElementById('btn-open-add-song');
        if (btnOpenAddSong) {
            setTimeout(() => btnOpenAddSong.click(), 300);
        }
    }
}
