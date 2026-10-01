// Microfone do celular vivo no Android: retoma o áudio quando o sistema o
// suspende (tela apagada, notificação) e avisa quando a faixa do microfone
// acaba (ligação, fone Bluetooth, outro app pegou o microfone).
import { state } from '../core/state.js';

// Fila de envio do WebSocket acima disto: a rede não está dando conta, e mais
// áudio na fila só atrasa o pong e derruba a conexão. O servidor tolera o buraco.
export const MAX_BUFFERED_BYTES = 256 * 1024;

export function micRunning() {
    const manager = state.audioManager;
    if (!manager || !manager.audioContext || manager.audioContext.state !== 'running') return false;
    const stream = manager.localStream;
    return !!stream && stream.getAudioTracks().some((t) => t.readyState === 'live');
}

export function stopMicHealth() {
    if (state.micHealthCleanup) {
        state.micHealthCleanup();
        state.micHealthCleanup = null;
    }
}

// onLost: a faixa do microfone acabou e só um toque do usuário religa
export function watchMicHealth(manager, onLost) {
    stopMicHealth();
    const ctx = manager.audioContext;
    const tracks = manager.localStream ? manager.localStream.getAudioTracks() : [];

    const resume = () => {
        if (ctx.state === 'running' || ctx.state === 'closed') return;
        if (document.visibilityState !== 'visible') return;
        ctx.resume().catch((e) => console.warn('Não retomou o áudio do microfone:', e));
    };
    const onVisibility = () => {
        if (document.visibilityState === 'visible') resume();
    };
    const lost = () => {
        stopMicHealth();
        onLost();
    };

    ctx.addEventListener('statechange', resume);
    document.addEventListener('visibilitychange', onVisibility);
    tracks.forEach((t) => t.addEventListener('ended', lost));

    state.micHealthCleanup = () => {
        ctx.removeEventListener('statechange', resume);
        document.removeEventListener('visibilitychange', onVisibility);
        tracks.forEach((t) => t.removeEventListener('ended', lost));
    };
}
