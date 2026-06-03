// Helper central de ícones (Lucide).
//
// O bundle Lucide é carregado como script clássico no <head> (window.lucide).
// Aqui expomos duas funções:
//   - renderIcons(root): hidrata os placeholders <i data-lucide="nome"> que
//     existirem no DOM (estáticos do index.html ou inseridos dinamicamente),
//     trocando-os pelo <svg> correspondente.
//   - iconHtml(name, opts): retorna a string de um placeholder de ícone para
//     ser concatenada em innerHTML de conteúdo dinâmico. Após inserir, chame
//     renderIcons() para materializar os SVGs.
//
// Convenção visual: todos os ícones herdam a cor do texto (currentColor) e o
// tamanho via classe `.lucide-icon` (ou modificadores), mantendo o traço fino
// e consistente em todo o app.

export function renderIcons(root = document) {
    const lucide = window.lucide;
    if (!lucide || typeof lucide.createIcons !== 'function') return;
    // createIcons varre todo o documento procurando [data-lucide]; o root é
    // aceito apenas para legibilidade da intenção de chamada.
    lucide.createIcons({
        attrs: { 'stroke-width': 2 },
    });
}

export function iconHtml(name, { size, cls = '', stroke = 2 } = {}) {
    const classes = ['lucide-icon', ...(cls ? cls.split(/\s+/) : [])].join(' ');
    const sizeAttr = size ? ` width="${size}" height="${size}"` : '';
    return `<i data-lucide="${name}" class="${classes}"${sizeAttr} stroke-width="${stroke}"></i>`;
}
