// Tema claro/escuro. A escolha fica neste aparelho (localStorage); sem escolha,
// a TV abre no escuro (as cores claras ficam lavadas na tela grande) e o resto
// no claro. O <head> do index.html já aplica a escolha salva antes de pintar.

import { isTvBrowser } from './config.js';
import { iconSvg } from './icons.js';

const STORAGE_KEY = 'karaoke_theme';
const THEME_COLOR = { light: '#f4ecd8', dark: '#221c16' };

function savedTheme() {
    try {
        const t = localStorage.getItem(STORAGE_KEY);
        return t === 'dark' || t === 'light' ? t : null;
    } catch (e) {
        return null;
    }
}

export function currentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', THEME_COLOR[theme]);
    const btn = document.getElementById('btn-theme');
    if (btn) {
        const next = theme === 'dark' ? 'claro' : 'escuro';
        btn.innerHTML = iconSvg(theme === 'dark' ? 'sun' : 'moon');
        btn.setAttribute('aria-label', `Tema ${next}`);
        btn.title = `Tema ${next}`;
    }
}

export function initTheme() {
    applyTheme(savedTheme() || (isTvBrowser ? 'dark' : 'light'));
    const btn = document.getElementById('btn-theme');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const theme = currentTheme() === 'dark' ? 'light' : 'dark';
        try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) { /* sem storage: vale só agora */ }
        applyTheme(theme);
    });
}
