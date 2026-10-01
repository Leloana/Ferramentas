// Reações da plateia na TV: o celular de quem não está cantando manda um dos
// três ícones e ele sobe pela tela com o apelido de quem mandou.
import { iconSvg } from '../core/icons.js';
import { micLabel } from '../lobby/lobby.js';

// os mesmos três do servidor (REACTIONS em server/ws/room.py)
export const REACTION_KINDS = ['heart', 'flame', 'star'];
// TV fraca: acima disso a reação nova é descartada até alguma sair da tela
const MAX_ON_SCREEN = 12;
const FLOAT_MS = 2600;

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
    node.className = `reaction reaction--${kind}`;
    // posição e balanço sorteados: várias reações seguidas não sobem em fila
    node.style.left = `${6 + Math.random() * 88}%`;
    node.style.setProperty('--sway', `${Math.round((Math.random() - 0.5) * 80)}px`);
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
