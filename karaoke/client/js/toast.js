import { iconSvg } from './icons.js';
import { myRole } from './config.js';

// No celular (tela estreita ou modo microfone) só erros viram aviso:
// confirmações e avisos de navegação cobrem o topo da tela sem ajudar.
function isCompactScreen() {
    return myRole === 'mic' || (window.matchMedia && window.matchMedia('(max-width: 700px)').matches);
}

export function showToast(message, type = 'info') {
    if (type !== 'error' && isCompactScreen()) return;

    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const TOAST_ICONS = { success: 'check', error: 'cross', warning: 'warning', info: 'info' };

    const iconDiv = document.createElement('div');
    iconDiv.className = 'toast-icon';
    iconDiv.innerHTML = iconSvg(TOAST_ICONS[type] || 'info');

    const contentDiv = document.createElement('div');
    contentDiv.className = 'toast-content';
    contentDiv.innerHTML = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close';
    closeBtn.innerHTML = iconSvg('close');
    closeBtn.addEventListener('click', () => {
        toast.classList.add('fading-out');
        setTimeout(() => toast.remove(), 300);
    });

    toast.appendChild(iconDiv);
    toast.appendChild(contentDiv);
    toast.appendChild(closeBtn);

    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) {
            toast.classList.add('fading-out');
            setTimeout(() => toast.remove(), 300);
        }
    }, 4700);
}
