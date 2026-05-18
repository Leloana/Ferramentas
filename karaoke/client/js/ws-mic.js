import { state } from './state.js';
import { myRoom } from './config.js';
import { showToast } from './toast.js';

export function connectMobileMicrophoneWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${myRoom}?role=mic`;

    state.mobileWs = new WebSocket(wsUrl);
    state.mobileWs.binaryType = 'arraybuffer';

    state.mobileWs.onopen = () => {
        document.getElementById('mobile-song-title').innerText = "Aguardando início...";
        document.getElementById('mobile-status-text').innerHTML = `🎙️ Microfone Pareado (Sala <span style="color: #a855f7; font-weight: 800;">${myRoom}</span>)`;
        showToast("Microfone pareado com sucesso!", "success");
    };

    state.mobileWs.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'pairing_status') {
            if (data.status === 'paired') {
                document.getElementById('mobile-status-text').innerHTML = `🎙️ Pareado e Pronto (Sala <span style="color: #a855f7; font-weight: 800;">${myRoom}</span>)`;
            } else if (data.status === 'unpaired') {
                document.getElementById('mobile-status-text').innerHTML = `<span style="color: var(--error); font-weight: 800;">⚠️ TV Desconectada (Sala ${myRoom})</span>`;
            }
        } else if (data.type === 'singing_state') {
            state.isSingingActive = data.active;
        } else if (data.type === 'segment_start') {
            const lyrContainer = document.getElementById('mobile-lyrics-container');
            if (lyrContainer) lyrContainer.style.display = 'flex';

            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) lyrText.innerText = data.lyrics;

            if (data.song_title) {
                document.getElementById('mobile-song-title').innerText = data.song_title;
            }
        } else if (data.type === 'segment_result') {
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                lyrText.innerHTML = `Segmento Anterior: <span style="color: #fde047; font-weight: 900;">${data.score}%</span><br><span style="font-size: 0.95rem; color: var(--dim); font-weight: 500;">Precisão Geral: ${data.total_score}%</span>`;
            }
        } else if (data.type === 'outro_start') {
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                lyrText.innerHTML = `🎸 FINALIZANDO APRESENTAÇÃO<br><span style="font-size: 1rem; color: #a855f7; font-weight: 800;">Você deu o seu show! ⚡</span><br><span style="font-size: 0.9rem; color: var(--dim);">Aguardando pontuação final...</span>`;
            }
        } else if (data.type === 'game_over') {
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                lyrText.innerHTML = `🎉 JOGO CONCLUÍDO!<br>Média Final: <span style="color: #fde047; font-weight: 900; font-size: 1.4rem;">${data.total_score}%</span>`;
            }
        }
    };

    state.mobileWs.onclose = () => {
        document.getElementById('mobile-status-text').innerHTML = `<span style="color: var(--error); font-weight: 800;">❌ Conexão Perdida. Reconectando...</span>`;
        setTimeout(connectMobileMicrophoneWebSocket, 3000);
    };
}
