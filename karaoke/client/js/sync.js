import { state } from './state.js';
import { dom } from './dom.js';

export function updateSyncDisplay() {
    const valStr = (state.syncOffset > 0 ? '+' : '') + (state.syncOffset * 1000).toFixed(0) + 'ms';
    if (dom.syncValueEl) dom.syncValueEl.innerText = valStr;
    const statsSync = document.getElementById('stats-sync-value');
    if (statsSync) statsSync.innerText = valStr;
}

export function initSyncControls() {
    const { btnSyncMinus, btnSyncPlus, backingVolumeSlider, backingVolumeValue, audioPlayer } = dom;

    if (btnSyncMinus) btnSyncMinus.onclick = () => { state.syncOffset -= 0.1; updateSyncDisplay(); };
    if (btnSyncPlus) btnSyncPlus.onclick = () => { state.syncOffset += 0.1; updateSyncDisplay(); };

    if (backingVolumeSlider) {
        backingVolumeSlider.oninput = (e) => {
            const val = parseFloat(e.target.value);
            if (state.audioManager) {
                state.audioManager.setVolume(val);
            } else {
                audioPlayer.volume = val;
            }
            backingVolumeValue.innerText = Math.round(val * 100) + '%';
            localStorage.setItem('karaoke_backing_volume', val);
        };

        const savedVolume = localStorage.getItem('karaoke_backing_volume');
        if (savedVolume !== null) {
            const vol = parseFloat(savedVolume);
            if (state.audioManager) {
                state.audioManager.setVolume(vol);
            } else {
                audioPlayer.volume = vol;
            }
            backingVolumeSlider.value = vol;
            backingVolumeValue.innerText = Math.round(vol * 100) + '%';
        } else {
            if (state.audioManager) {
                state.audioManager.setVolume(1.0);
            } else {
                audioPlayer.volume = 1.0;
            }
            backingVolumeSlider.value = 1.0;
            backingVolumeValue.innerText = '100%';
        }
    }
}

export function startTimeSync() {
    setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify({
                type: "playback_time",
                current_time: dom.audioPlayer.currentTime + state.syncOffset
            }));
        }
    }, 100);
}
