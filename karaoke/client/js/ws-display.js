import { state } from './state.js';
import { myRole, myRoom } from './config.js';
import { handleServerMessage } from './game-view.js';

export function connectDisplayWebSocket() {
    if (myRole !== 'display') return;
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${myRoom}?role=display`;

    state.ws = new WebSocket(wsUrl);
    state.ws.binaryType = 'arraybuffer';

    state.ws.onopen = () => {
        console.log("WebSocket do Display conectado na sala:", myRoom);
    };

    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };

    state.ws.onclose = () => {
        console.log("WebSocket do Display desconectado. Tentando reconectar...");
        if (state.currentAppState === 'idle') {
            setTimeout(connectDisplayWebSocket, 3000);
        }
    };

    state.ws.onerror = (err) => {
        console.error("Erro no WebSocket do Display:", err);
    };
}
