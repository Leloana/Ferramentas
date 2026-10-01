// WebSocket do celular-microfone (role=mic): abre, repassa as mensagens e
// reconecta sozinho quando a rede cai.
import { state } from '../state.js';
import { myRoom, MIC_REPLACED_CODE } from '../config.js';
import { escapeHtml } from '../html.js';
import { handleMicMessage } from './mic-messages.js';

const RECONNECT_MS = 3000;

// Linha de status no topo do celular (sala, apelido, conexão)
export function setMicStatus(html) {
    const el = document.getElementById('mobile-status-text');
    if (el) el.innerHTML = html;
}

export function connectMobileMicrophoneWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${encodeURIComponent(myRoom)}?role=mic`;

    state.mobileWs = new WebSocket(wsUrl);
    state.mobileWs.binaryType = 'arraybuffer';

    state.mobileWs.onopen = () => {
        document.getElementById('mobile-song-title').innerText = "Karaoke";
        setMicStatus(`Sala <span class="mic-status__name">${escapeHtml(myRoom)}</span>`);
    };

    state.mobileWs.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            console.error("Payload do microfone malformado:", e);
            return;
        }
        handleMicMessage(data);
    };

    state.mobileWs.onclose = (event) => {
        if (event && event.code === MIC_REPLACED_CODE) {
            // este celular entrou de novo por outra conexão (outra aba): não briga por ela
            setMicStatus(`<span class="mic-status--error">Microfone aberto em outra aba</span>`);
            return;
        }
        setMicStatus(`<span class="mic-status--error">Conexão perdida. Reconectando...</span>`);
        setTimeout(connectMobileMicrophoneWebSocket, RECONNECT_MS);
    };
}
