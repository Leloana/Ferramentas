// Reações da plateia na TV: o celular de quem não está cantando manda um dos
// três ícones e ele sobe pela tela com o apelido de quem mandou.
import { iconSvg } from '../core/icons.js';
import { micLabel } from '../lobby/lobby.js';

// os mesmos três do servidor (REACTIONS em server/ws/room.py)
export const REACTION_KINDS = ['heart', 'flame', 'star'];
// TV fraca: acima disso a reação nova é descartada até alguma sair da tela
const MAX_ON_SCREEN = 12;
const FLOAT_MS = 2600;
const SWAYS = ['left', 'straight', 'right'];

let layer = null;

function reactionLayer() {
    if (!layer || !layer.isConnected) {
        layer = document.createElement('div');
        layer.className = 'reaction-layer';
        layer.setAttribute('aria-hidden', 'true');
        document.body.append(layer);
    }
    return layer;
}

export function showReaction(kind, from) {
    if (REACTION_KINDS.indexOf(kind) === -1) return;
    const box = reactionLayer();
    if (box.childElementCount >= MAX_ON_SCREEN) return;
    const node = document.createElement('div');
    // posição e trajetória sorteadas: várias reações seguidas não sobem em fila.
    // Trajetórias fixas no CSS: var() dentro de @keyframes pode tirar a animação
    // da GPU no Chromium antigo da TV.
    node.className = `reaction reaction--${kind} reaction--${SWAYS[Math.floor(Math.random() * SWAYS.length)]}`;
    node.style.left = `${6 + Math.random() * 88}%`;
    node.innerHTML = iconSvg(kind);
    if (from) {
        const name = document.createElement('span');
        name.className = 'reaction__name';
        name.textContent = micLabel(from);
        node.append(name);
    }
    box.append(node);
    // o animationend não vem com a aba em segundo plano: o tempo garante a saída
    const done = () => node.remove();
    node.addEventListener('animationend', done);
    setTimeout(done, FLOAT_MS + 400);
}

export function clearReactions() {
    if (layer) layer.replaceChildren();
}
