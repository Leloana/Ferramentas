// Mantém a tela acesa (Screen Wake Lock). No celular-microfone a tela apagava
// no meio da música e o navegador parava de mandar o áudio do mic; na TV, o
// descanso de tela podia entrar durante a partida.
//
// O navegador solta o bloqueio sozinho quando a aba some (troca de app, tela
// bloqueada): pedimos de novo ao voltar, enquanto `wanted` estiver ligado.
import { state } from './state.js';

async function request() {
    if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    try {
        state.wakeLock = await navigator.wakeLock.request('screen');
        state.wakeLock.addEventListener('release', () => { state.wakeLock = null; });
    } catch (e) {
        // sem permissão / economia de bateria: segue sem, não é erro para o usuário
        console.warn('Wake Lock indisponível:', e && e.message);
    }
}

export function keepScreenOn() {
    state.wakeLockWanted = true;
    if (!state.wakeLock) request();
}

export function allowScreenOff() {
    state.wakeLockWanted = false;
    if (state.wakeLock) {
        state.wakeLock.release().catch(() => {});
        state.wakeLock = null;
    }
}

document.addEventListener('visibilitychange', () => {
    if (state.wakeLockWanted && !state.wakeLock) request();
});
