import { state } from '../core/state.js';
import { myRole, myRoom, DISPLAY_REPLACED_CODE } from '../core/config.js';
import { handleServerMessage } from '../game/server-messages.js';

export function connectDisplayWebSocket() {
    if (myRole !== 'display') return;
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${encodeURIComponent(myRoom)}?role=display`;

    state.ws = new WebSocket(wsUrl);
    state.ws.binaryType = 'arraybuffer';

    state.ws.onopen = () => {
        console.log("WebSocket do Display conectado na sala:", myRoom);
    };

    state.ws.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch (e) { return; }
        handleServerMessage(data);
    };

    state.ws.onclose = (event) => {
        console.log("WebSocket do Display desconectado. Tentando reconectar...");
        // outra aba/tela assumiu a sala: reconectar derrubaria a outra, em loop
        if (event && event.code === DISPLAY_REPLACED_CODE) return;
        if (state.currentAppState === 'idle') {
            setTimeout(connectDisplayWebSocket, 3000);
        }
    };

    state.ws.onerror = (err) => {
        console.error("Erro no WebSocket do Display:", err);
    };
}
