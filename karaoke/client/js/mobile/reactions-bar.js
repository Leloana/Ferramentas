// Reações da plateia no celular: três botões que só aparecem para quem está
// assistindo a música (não canta). A TV mostra o ícone subindo (game/reactions.js).
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { REACTION_KINDS } from '../game/reactions.js';

// um pouco acima do intervalo do servidor (REACTION_MIN_INTERVAL_SEC): toque
// descartado lá não acenderia o botão aqui
const COOLDOWN_MS = 500;
const LABELS = { heart: 'Coração', flame: 'Fogo', star: 'Estrela' };

let lastSent = 0;

function bar() {
    return document.getElementById('mobile-reactions');
}

function send(kind, btn) {
    const now = Date.now();
    if (now - lastSent < COOLDOWN_MS) return;
    const ws = state.mobileWs;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    lastSent = now;
    ws.send(JSON.stringify({ type: 'reaction', kind }));
    btn.classList.remove('reaction-btn--sent');
    void btn.offsetWidth;
    btn.classList.add('reaction-btn--sent');
}

export function initReactionsBar() {
    const box = bar();
    if (!box) return;
    box.replaceChildren();
    REACTION_KINDS.forEach((kind) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `reaction-btn reaction-btn--${kind}`;
        btn.setAttribute('aria-label', LABELS[kind]);
        btn.innerHTML = iconSvg(kind);
        btn.addEventListener('click', () => send(kind, btn));
        box.append(btn);
    });
}

// visível na partida para quem não está cantando
export function setReactionsVisible(visible) {
    const box = bar();
    if (box) box.hidden = !visible;
}
