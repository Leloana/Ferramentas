// Ícones próprios do Karaoke (sem emojis nem bibliotecas de terceiros).
//
// Desenhados à mão numa grade 24×24, traço de tinta 1.6 com pontas retas,
// para combinar com os botões de canto reto e a estética de partitura.
// Herdam a cor do texto (currentColor) e escalam com a fonte (.ico).
//
//   - No HTML estático: <i data-icon="mic"></i>  → renderIcons() troca pelo <svg>.
//   - Em HTML montado no JS: iconSvg('mic') devolve a string do <svg>.

const P = {
    // navegação
    songs: '<path d="M5 3.5h10l4 4v13H5z"/><path d="M15 3.5v4h4"/><path d="M8 11.5h8M8 14h8M8 16.5h8"/><circle cx="10" cy="16.5" r="1.3" fill="currentColor" stroke="none"/><path d="M11.3 16.5V10"/>',
    add: '<path d="M12 5v14M5 12h14"/>',
    'add-box': '<path d="M4 4h16v16H4z"/><path d="M12 8v8M8 12h8"/>',
    back: '<path d="M20 12H5"/><path d="M11 6l-6 6 6 6"/>',
    next: '<path d="M4 12h15"/><path d="M13 6l6 6-6 6"/>',
    'chevron-down': '<path d="M6 9l6 6 6-6"/>',
    'chevron-up': '<path d="M6 15l6-6 6 6"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    search: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>',

    // microfones e dispositivos
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0"/><path d="M12 17v4M8.5 21h7"/>',
    'mic-off': '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0"/><path d="M12 17v4M8.5 21h7"/><path d="M4 4l16 16"/>',
    phone: '<path d="M7.5 2.5h9v19h-9z"/><path d="M11 18.5h2"/>',
    pc: '<path d="M3 4.5h18v11H3z"/><path d="M12 15.5v4M8 19.5h8"/>',
    qr: '<path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4z"/><path d="M14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z"/>',
    speaker: '<path d="M6 3h12v18H6z"/><circle cx="12" cy="14.5" r="3.5"/><circle cx="12" cy="7" r="1.2"/>',
    headphones: '<path d="M4 16v-4a8 8 0 0 1 16 0v4"/><path d="M4 15h3.5v6H4zM16.5 15H20v6h-3.5z"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><path d="M15 4.8a3.5 3.5 0 0 1 0 6.4M17 14.3c2.3.8 4 2.9 4 5.7"/>',

    // ajustes da faixa
    volume: '<path d="M4 9h4l5-4.5v15L8 15H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
    pitch: '<ellipse cx="8" cy="17.5" rx="3.2" ry="2.4" transform="rotate(-20 8 17.5)"/><path d="M11 16.5V4l7 2.5"/>',
    metronome: '<path d="M8.5 3.5h7l3.5 17H5z"/><path d="M5.8 17h12.4"/><path d="M12 17l4.5-10"/><path d="M15.2 9.5h2.5"/>',
    'sync-word': '<path d="M3 17h3M18 17h3"/><path d="M8.5 13h7v6h-7z"/><path d="M3 9h18" opacity=".5"/>',
    'sync-verse': '<path d="M3 13h18v6H3z"/><path d="M3 9h18" opacity=".5"/>',
    'score-words': '<path d="M4 6h16M4 10.5h16M4 15h10"/><path d="M15.5 17.5l2 2 3.5-4"/>',

    // cards e listas
    refresh: '<path d="M19 12a7 7 0 1 1-2.05-4.95"/><path d="M19 4v4h-4"/>',
    edit: '<path d="M4 20l1-4.5L16 4.5 19.5 8 8.5 19z"/><path d="M13.5 7l3.5 3.5"/>',
    trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6.5 7l1 13.5h9l1-13.5"/><path d="M10 11v6M14 11v6"/>',
    folder: '<path d="M3 5.5h6l2 2.5h10v11.5H3z"/>',
    save: '<path d="M4 4h13l3 3v13H4z"/><path d="M8 4v5h7V4"/><path d="M7.5 20v-6h9v6"/>',
    settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><path d="M14 4.5h4v5h-4zM6 14.5h4v5H6z"/>',
    lyrics: '<path d="M5 3.5h14v17H5z"/><path d="M8 8h8M8 11.5h8M8 15h5"/>',
    'lrc-file': '<path d="M5 3.5h10l4 4v13H5z"/><path d="M15 3.5v4h4"/><path d="M8.5 12v4.5h2.5M12.5 12h1.5v4.5M15.5 12.5a1.5 1.5 0 0 0 0 3.5"/>',
    video: '<path d="M3 5.5h18v13H3z"/><path d="M10 9v6l5-3z"/>',
    play: '<path d="M7 4.5v15l12-7.5z"/>',
    pause: '<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/>',

    note: '<ellipse cx="8.5" cy="17.5" rx="3.4" ry="2.5" transform="rotate(-20 8.5 17.5)" fill="currentColor" stroke="none"/><path d="M11.6 16.6V3.5c2.5 1.4 5.8 2.6 6.4 6.2"/>',

    // estados (fila, letra, anotação)
    check: '<path d="M4.5 12.5l5 5 10-11"/>',
    cross: '<path d="M6 6l12 12M18 6L6 18"/>',
    hum: '<path d="M2.5 12c1.6-3.5 3.2-3.5 4.8 0s3.2 3.5 4.8 0 3.2-3.5 4.8 0 3.2 3.5 4.8 0"/>',
    hourglass: '<path d="M6.5 3.5h11M6.5 20.5h11"/><path d="M8 3.5c0 5 8 5.5 8 8.5s-8 3.5-8 8.5M16 3.5c0 5-8 5.5-8 8.5s8 3.5 8 8.5"/>',
    download: '<path d="M12 4v11"/><path d="M7 10.5l5 5 5-5"/><path d="M4.5 20h15"/>',
    split: '<path d="M3 12h4l3-6h11M10 18h11l-3-6h-2"/><path d="M18 3.5L21 6l-3 2.5M18 15.5l3 2.5-3 2.5"/>',
    target: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3.5M12 18.5V22M2 12h3.5M18.5 12H22"/>',
    seal: '<path d="M12 3l2.3 2.2 3.1-.4.5 3.1 2.7 1.6-1.4 2.8 1.4 2.8-2.7 1.6-.5 3.1-3.1-.4L12 21l-2.3-2.2-3.1.4-.5-3.1-2.7-1.6L4.8 12 3.4 9.2l2.7-1.6.5-3.1 3.1.4z"/><path d="M8.8 12.2l2.2 2.2 4.2-4.6"/>',
    warning: '<path d="M12 3.5L21.5 20h-19z"/><path d="M12 10v4.5M12 16.8v.4"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v6M12 7.3v.4"/>',
    robot: '<path d="M5 8h14v11H5z"/><path d="M12 4.5V8M9 12.5v1.5M15 12.5v1.5M9.5 16.5h5"/><path d="M3 12v3M21 12v3"/>',
    bolt: '<path d="M13.5 2.5L5.5 13.5h6l-1 8 8-11h-6z"/>',
    flame: '<path d="M12 21c-4 0-6.5-2.7-6.5-6.2 0-3.8 3-5.6 3.5-9.3 2.6 1.6 3.3 4 3 6 1.2-.8 2-2.1 2.2-3.5 2.2 2 3.8 4.4 3.8 6.8C18.5 18.3 16 21 12 21z"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.5l3.5 2"/>',

    // palco e pódio
    crown: '<path d="M3.5 18.5l-1-11 5.5 4.5L12 5l4 7 5.5-4.5-1 11z"/><path d="M4 21h16"/>',
    fermata: '<path d="M3.5 16.5a8.5 8.5 0 0 1 17 0"/><circle cx="12" cy="15.3" r="1.4" fill="currentColor" stroke="none"/>',
    'double-bar': '<path d="M5 4v16M5 4h14M5 20h14M16 4v16"/><path d="M19 4v16" stroke-width="3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 21c0-4.4 3.4-7.5 7.5-7.5s7.5 3.1 7.5 7.5"/>',
    eye: '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    // perfil, recordes e tela para print
    trophy: '<path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M7 6H4v1.5A3.5 3.5 0 0 0 7.5 11M17 6h3v1.5a3.5 3.5 0 0 1-3.5 3.5"/><path d="M12 14v3.5M8.5 20.5h7M10 17.5h4v3h-4z"/>',
    star: '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 17l-5.2 2.7 1-5.9-4.3-4.1 5.9-.8z"/>',
    camera: '<path d="M3.5 7.5h4l1.5-2.5h6l1.5 2.5h4v12h-17z"/><circle cx="12" cy="13" r="3.8"/>',
    shuffle: '<path d="M3 7h4l10 10h4M3 17h4l3-3M14 10l3-3h4"/><path d="M18 4l3 3-3 3M18 14l3 3-3 3"/>',
    image: '<path d="M3.5 4.5h17v15h-17z"/><circle cx="9" cy="9.5" r="1.8"/><path d="M3.5 17l5-5 4 4 3-3 5 5"/>',
    gauge: '<path d="M3.5 17a8.5 8.5 0 1 1 17 0"/><path d="M12 17l4-6"/><circle cx="12" cy="17" r="1.3" fill="currentColor" stroke="none"/>',
};

export const ICON_NAMES = Object.keys(P);

export function iconSvg(name, cls = '') {
    const body = P[name];
    if (!body) return '';
    const classes = ['ico', `ico--${name}`].concat(cls ? cls.split(/\s+/) : []).join(' ');
    return `<svg class="${classes}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="square" stroke-linejoin="miter" aria-hidden="true" focusable="false">${body}</svg>`;
}

// Troca os <i data-icon="nome"> do documento (ou de `root`) pelo <svg> do ícone.
export function renderIcons(root = document) {
    // <template> guarda o conteúdo à parte: hidrata também (cards clonados depois)
    root.querySelectorAll('template').forEach((tpl) => renderIcons(tpl.content));
    root.querySelectorAll('i[data-icon]').forEach((el) => {
        const html = iconSvg(el.getAttribute('data-icon'), el.className);
        if (!html) return;
        const tpl = document.createElement('template');
        tpl.innerHTML = html;
        el.replaceWith(tpl.content.firstChild);
    });
}
