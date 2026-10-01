// WebSocket do celular-microfone (role=mic): abre, repassa as mensagens e
// reconecta sozinho quando a rede cai.
//
// Android com a tela apagada segura um socket meio aberto por minutos e estrangula
// os timers da aba. Por isso o celular manda um ping a cada 10 s e, sem resposta do
// servidor em 25 s, troca de conexão. Ao voltar a tela, reconecta na hora.
import { state } from '../core/state.js';
import { myRoom, MIC_REPLACED_CODE } from '../core/config.js';
import { escapeHtml } from '../core/html.js';
import { handleMicMessage } from './mic-messages.js';

const RECONNECT_MS = 3000;
const PING_EVERY_MS = 10000;
const SERVER_SILENCE_MS = 25000;

// Linha de status no topo do celular (sala, apelido, conexão)
export function setMicStatus(html) {
    const el = document.getElementById('mobile-status-text');
    if (el) el.innerHTML = html;
}

function clearReconnect() {
    if (state.micReconnectTimer) {
        clearTimeout(state.micReconnectTimer);
        state.micReconnectTimer = null;
    }
}

function socketAlive() {
    const ws = state.mobileWs;
    return !!ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING);
}

// Abandona a conexão atual (os eventos dela passam a ser ignorados) e abre outra
function reconnectNow() {
    clearReconnect();
    const old = state.mobileWs;
    state.mobileWs = null;
    if (old) {
        try { old.close(); } catch (e) { /* já fechado */ }
    }
    connectMobileMicrophoneWebSocket();
}

function heartbeat() {
    const ws = state.mobileWs;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (Date.now() - state.micLastServerAt > SERVER_SILENCE_MS) {
        console.warn('Servidor sem responder: trocando a conexão do microfone');
        reconnectNow();
        return;
    }
    ws.send(JSON.stringify({ type: 'ping' }));
}

function hookVisibility() {
    if (state.micVisibilityHooked) return;
    state.micVisibilityHooked = true;
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible' || state.micReplaced) return;
        // a tela voltou: não espera o timer estrangulado da aba em segundo plano
        if (!socketAlive()) reconnectNow();
        else heartbeat();
    });
}

export function connectMobileMicrophoneWebSocket() {
    clearReconnect();
    hookVisibility();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${encodeURIComponent(myRoom)}?role=mic`;

    const ws = new WebSocket(wsUrl);
    state.mobileWs = ws;
    ws.binaryType = 'arraybuffer';
    state.micLastServerAt = Date.now();
    if (!state.micHeartbeatTimer) state.micHeartbeatTimer = setInterval(heartbeat, PING_EVERY_MS);

    ws.onopen = () => {
        if (state.mobileWs !== ws) return;
        state.micLastServerAt = Date.now();
        document.getElementById('mobile-song-title').innerText = "Karaoke";
        setMicStatus(`Sala <span class="mic-status__name">${escapeHtml(myRoom)}</span>`);
    };

    ws.onmessage = (event) => {
        if (state.mobileWs !== ws) return;
        state.micLastServerAt = Date.now();
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            console.error("Payload do microfone malformado:", e);
            return;
        }
        handleMicMessage(data);
    };

    ws.onclose = (event) => {
        // conexão que já foi trocada por outra: não reconecta por cima da nova
        if (state.mobileWs !== ws) return;
        if (event && event.code === MIC_REPLACED_CODE) {
            // este celular entrou de novo por outra conexão (outra aba): não briga por ela
            state.micReplaced = true;
            setMicStatus(`<span class="mic-status--error">Microfone aberto em outra aba</span>`);
            return;
        }
        setMicStatus(`<span class="mic-status--error">Conexão perdida. Reconectando...</span>`);
        state.micReconnectTimer = setTimeout(connectMobileMicrophoneWebSocket, RECONNECT_MS);
    };
}
