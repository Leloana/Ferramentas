// Linha do tempo da partida para a gravação (server/recorder.py): a TV avisa
// play/pausa/seek/velocidade, volumes e sincronia. Só informativo — nada no
// servidor depende disso para pontuar.
import { state } from './state.js';
import { dom } from './dom.js';

export function sendPlayerEvent(event, value) {
    const ws = state.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN || state.currentAppState === 'idle') return;
    const audio = dom.audioPlayer;
    try {
        ws.send(JSON.stringify({
            type: 'player_event',
            event,
            t: audio ? Math.round(audio.currentTime * 1000) / 1000 : null,
            value: value === undefined ? null : value,
        }));
    } catch (e) { /* socket fechando: evento perdido, sem problema */ }
}

// Liga os eventos do <audio> da partida (o elemento é trocado a cada partida).
export function attachPlayerEvents() {
    const audio = dom.audioPlayer;
    if (!audio || audio._eventsAttached) return;
    audio._eventsAttached = true;
    audio.addEventListener('play', () => sendPlayerEvent('play'));
    audio.addEventListener('pause', () => sendPlayerEvent('pause'));
    audio.addEventListener('seeked', () => sendPlayerEvent('seek', Math.round(audio.currentTime * 1000) / 1000));
    audio.addEventListener('ratechange', () => sendPlayerEvent('rate', audio.playbackRate));
    audio.addEventListener('stalled', () => sendPlayerEvent('stalled'));
    audio.addEventListener('waiting', () => sendPlayerEvent('buffering'));
}

// Aparelho: navegador, sistema e como o microfone foi aberto (para separar
// "cantou mal" de "o celular falhou" ao calibrar).
export function deviceInfo(stream) {
    const info = {
        user_agent: navigator.userAgent,
        platform: navigator.platform || null,
        // tamanho da tela em px CSS (diagnóstico de layout na TV)
        viewport: [window.innerWidth, window.innerHeight, window.devicePixelRatio || 1],
    };
    try {
        const track = stream && stream.getAudioTracks && stream.getAudioTracks()[0];
        if (track && track.getSettings) {
            const st = track.getSettings();
            info.track = {
                sampleRate: st.sampleRate, channelCount: st.channelCount, latency: st.latency,
                echoCancellation: st.echoCancellation, noiseSuppression: st.noiseSuppression,
                autoGainControl: st.autoGainControl,
            };
        }
    } catch (e) { /* navegador sem getSettings */ }
    return info;
}
