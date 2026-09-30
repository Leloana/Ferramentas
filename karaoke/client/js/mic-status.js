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

    // Botão aceso = fonte de microfone em uso (layout.css: .tab-btn--mic-on)
    const markButtons = (pcOn, mobileOn) => {
        if (btnForcePc) btnForcePc.classList.toggle('tab-btn--mic-on', pcOn);
        if (btnForceMobile) btnForceMobile.classList.toggle('tab-btn--mic-on', mobileOn);
    };

    if (isSoloMobileMode) {
        dot.hidden = true;
        text.innerText = 'Modo Solo (Celular)';
        setBadgeClass('mic-badge--solo');
        if (btnForcePc) btnForcePc.hidden = true;
        if (btnForceMobile) btnForceMobile.hidden = true;
        return;
    }

    dot.hidden = false;
    dot.classList.add('mic-badge-dot');

    if (state.isMobileMicrophoneConnected && state.localStreamForced) {
        text.innerText = 'Dispositivo + Celular';
        setBadgeClass('mic-badge--both');
        markButtons(true, true);
    } else if (state.isMobileMicrophoneConnected) {
        text.innerText = 'Celular Ativo';
        setBadgeClass('mic-badge--paired');
        markButtons(false, true);
    } else if (state.localStreamForced) {
        text.innerText = 'Mic do dispositivo';
        setBadgeClass('mic-badge--pc');
        markButtons(true, false);
    } else {
        text.innerText = 'Sem Mic';
        setBadgeClass('mic-badge--idle');
        markButtons(false, false);
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
