import { state } from './state.js';
import { myRole, isSoloMobileMode } from './config.js';

export function updateMicStatusPanel() {
    if (myRole !== 'display') return;
    const badge = document.getElementById('mic-active-badge');
    const dot = document.getElementById('mic-badge-dot');
    const text = document.getElementById('mic-badge-text');
    const btnForcePc = document.getElementById('btn-force-pc-mic');
    const btnForceMobile = document.getElementById('btn-open-pairing');

    if (!dot || !text) return;

    const setBadgeClass = (cls) => {
        if (!badge) return;
        badge.classList.remove('mic-badge--idle', 'mic-badge--pc', 'mic-badge--paired', 'mic-badge--both', 'mic-badge--solo');
        badge.classList.add('mic-badge', cls);
    };

    if (isSoloMobileMode) {
        dot.style.display = 'none';
        text.innerText = 'Modo Solo (Celular)';
        setBadgeClass('mic-badge--solo');
        if (btnForcePc) btnForcePc.style.display = 'none';
        if (btnForceMobile) btnForceMobile.style.display = 'none';
        return;
    }

    dot.style.display = '';
    dot.classList.add('mic-badge-dot');

    if (state.isMobileMicrophoneConnected && state.localStreamForced) {
        text.innerText = 'PC + Celular';
        setBadgeClass('mic-badge--both');
        if (btnForcePc) btnForcePc.style.borderColor = '#3b82f6';
        if (btnForceMobile) btnForceMobile.style.borderColor = '#a855f7';
    } else if (state.isMobileMicrophoneConnected) {
        text.innerText = 'Celular Ativo';
        setBadgeClass('mic-badge--paired');
        if (btnForcePc) btnForcePc.style.borderColor = 'rgba(255,255,255,0.15)';
        if (btnForceMobile) btnForceMobile.style.borderColor = '#a855f7';
    } else if (state.localStreamForced) {
        text.innerText = 'PC Ativo';
        setBadgeClass('mic-badge--pc');
        if (btnForcePc) btnForcePc.style.borderColor = '#3b82f6';
        if (btnForceMobile) btnForceMobile.style.borderColor = 'rgba(255,255,255,0.15)';
    } else {
        text.innerText = 'Sem Mic';
        setBadgeClass('mic-badge--idle');
        if (btnForcePc) btnForcePc.style.borderColor = 'rgba(255,255,255,0.15)';
        if (btnForceMobile) btnForceMobile.style.borderColor = 'rgba(255,255,255,0.15)';
    }
}

export async function checkInitialMicPermission() {
    if (myRole !== 'display') return;
    try {
        if (navigator.permissions && navigator.permissions.query) {
            const status = await navigator.permissions.query({ name: 'microphone' });
            state.localStreamForced = (status.state === 'granted');
            updateMicStatusPanel();

            status.onchange = () => {
                state.localStreamForced = (status.state === 'granted');
                updateMicStatusPanel();
            };
        }
    } catch (e) {
        console.debug("navigator.permissions não suportado:", e);
    }
    updateMicStatusPanel();
}
