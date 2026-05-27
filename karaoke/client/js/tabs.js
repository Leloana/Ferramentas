// Helper declarativo de abas, reaproveitado por todos os seletores de abas.
//
// O estilo das abas já é dirigido por um atributo no container (ex.:
// `data-active-tab`, `data-upload-tab`, `data-editor-tab`) via CSS. Este helper
// apenas troca esse atributo ao clicar em cada botão, eliminando os handlers
// `onclick` duplicados que existiam em cada módulo.
//
// Markup esperado:
//   <div data-tabs="active-tab">           <!-- atributo a alternar, sem o prefixo data- -->
//     <button data-tab="songs">...</button>
//     <button data-tab="queue">...</button>
//   </div>
//
// Uso:
//   initTabs('selection-area', { onSelect: (tab) => { ... } });

export function initTabs(containerOrId, { onSelect } = {}) {
    const container = typeof containerOrId === 'string'
        ? document.getElementById(containerOrId)
        : containerOrId;
    if (!container) return null;

    const attr = 'data-' + (container.getAttribute('data-tabs') || 'active-tab');
    const buttons = Array.from(container.querySelectorAll('[data-tab]'));

    const select = (tab, { silent = false } = {}) => {
        container.setAttribute(attr, tab);
        if (!silent && typeof onSelect === 'function') onSelect(tab);
    };

    buttons.forEach((btn) => {
        btn.addEventListener('click', () => select(btn.getAttribute('data-tab')));
    });

    // Garante um estado inicial: respeita o que já estiver no HTML, senão usa a 1ª aba.
    if (!container.hasAttribute(attr) && buttons.length) {
        select(buttons[0].getAttribute('data-tab'), { silent: true });
    }

    return { select, container };
}
