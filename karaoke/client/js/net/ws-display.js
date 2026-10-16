import { state } from '../core/state.js';
import { myRole, myRoom, DISPLAY_REPLACED_CODE, DISPLAY_STALE_CODE, ROOM_TAKEN_CODE, displaySocketParams, isSoloMobileMode, saveEntry } from '../core/config.js';
import { showToast } from '../core/toast.js';
import { handleServerMessage } from '../game/server-messages.js';

function lobbyScreen() {
    return ['idle', 'waiting', 'game-over'].indexOf(state.currentAppState) !== -1;
}

export function connectDisplayWebSocket() {
    if (myRole !== 'display') return;
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${encodeURIComponent(myRoom)}?role=display&${displaySocketParams()}`;

    state.ws = new WebSocket(wsUrl);
    state.ws.binaryType = 'arraybuffer';

    state.ws.onopen = () => {
        console.log("WebSocket do Display conectado na sala:", myRoom);
        if (state.publishLobbyState) state.publishLobbyState();
    };

    state.ws.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch (e) { return; }
        handleServerMessage(data);
    };

    state.ws.onclose = (event) => {
        console.log("WebSocket do Display desconectado. Tentando reconectar...");
        // outra aba/tela assumiu a sala: reconectar derrubaria a outra, em loop
        if (event && (event.code === DISPLAY_REPLACED_CODE || event.code === DISPLAY_STALE_CODE)) return;
        if (event && event.code === ROOM_TAKEN_CODE) {
            if (isSoloMobileMode) {
                // celular no modo Sala: volta à entrada com o nome para trocar
                saveEntry({ room_name: '', taken: myRoom });
                window.location.href = '/';
                return;
            }
            showToast('Este nome de sala já está em uso.', 'error');
            return;
        }
        if (lobbyScreen()) {
            // confere de novo na hora: se a partida começou nesse meio-tempo, uma
            // conexão de lobby fecharia a partida no servidor
            setTimeout(() => { if (lobbyScreen()) connectDisplayWebSocket(); }, 3000);
        }
    };

    state.ws.onerror = (err) => {
        console.error("Erro no WebSocket do Display:", err);
    };
}
