// Lembrete de microfone desligado (TV/computador). O celular avisa quando liga,
// desliga ou muta (`mic_state`); o servidor manda `mic_states` para a TV.
//   - lobby: selo "Mic desligado"/"Mudo" na vaga do cantor (lobby.js);
//   - partida: aviso fixo no topo com quem está escalado e sem microfone.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { micLabel, PC_MIC, renderLobby } from '../lobby/lobby.js';

// Microfone de um celular: 'on' | 'muted' | 'off' (o do PC liga com a partida)
export function micStateOf(mic) {
    if (mic === PC_MIC || mic === 'Solo') return 'on';
    return (state.micStates && state.micStates[mic]) || 'off';
}

export function updateMicReminder() {
    const box = document.getElementById('mic-off-reminder');
    if (!box) return;
    const singing = state.currentAppState === 'singing' || state.currentAppState === 'scoring';
    const off = singing ? (state.activePlayers || []).filter((m) => micStateOf(m) !== 'on') : [];
    box.hidden = !off.length;
    if (!off.length) return;
    const muted = off.filter((m) => micStateOf(m) === 'muted');
    const parts = [];
    const dead = off.filter((m) => micStateOf(m) === 'off');
    if (dead.length) parts.push(`Ligue o microfone: ${dead.map(micLabel).join(', ')}`);
    if (muted.length) parts.push(`No mudo: ${muted.map(micLabel).join(', ')}`);
    box.innerHTML = iconSvg('mic-off');
    box.append(document.createTextNode(' ' + parts.join(' · ')));
}

export function onMicStates(states) {
    state.micStates = states || {};
    renderLobby();
    updateMicReminder();
}

export function initMicReminder() {
    const app = document.getElementById('app');
    if (app && window.MutationObserver) {
        new MutationObserver(updateMicReminder).observe(app, { attributes: true, attributeFilter: ['data-state'] });
    }
}
