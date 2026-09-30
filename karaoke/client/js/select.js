// Select personalizado (no lugar do menu nativo do navegador).
//
// O <select> original fica escondido e continua sendo a fonte da verdade: o
// formulário lê o valor dele e ele dispara `change` como antes. Por cima vai um
// botão + lista no estilo do app. Funciona com mouse, toque, teclado e controle
// remoto (as opções são <button>, então a navegação por setas do tv-nav.js
// percorre a lista; Voltar/Esc fecha só a lista).
//
// Uso: enhanceSelects(document) no bootstrap. Mudanças feitas por código
// (select.value = x, trocar as <option>, `hidden`, form.reset()) são refletidas.

import { iconSvg } from './icons.js';

const nativeValue = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
const OPEN_CLASS = 'cselect--open';

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
}

function selectedText(select) {
    const opt = select.options[select.selectedIndex];
    return opt ? opt.textContent : '';
}

function closeSelect(wrap, { focusButton = false } = {}) {
    if (!wrap.classList.contains(OPEN_CLASS)) return;
    wrap.classList.remove(OPEN_CLASS);
    wrap.querySelector('.cselect__button').setAttribute('aria-expanded', 'false');
    if (focusButton) wrap.querySelector('.cselect__button').focus();
}

// Fecha qualquer lista aberta. Devolve true se fechou alguma (tv-nav: "voltar").
export function closeOpenSelects() {
    const open = document.querySelectorAll(`.${OPEN_CLASS}`);
    open.forEach((wrap) => closeSelect(wrap, { focusButton: true }));
    return open.length > 0;
}

function buildList(select, wrap) {
    const list = wrap.querySelector('.cselect__list');
    list.replaceChildren();
    Array.prototype.forEach.call(select.options, (opt, idx) => {
        const item = el('button', 'cselect__option');
        item.type = 'button';
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(idx === select.selectedIndex));
        item.disabled = opt.disabled;
        item.innerHTML = iconSvg('check', 'cselect__check');
        item.append(el('span', null, opt.textContent));
        item.addEventListener('click', () => {
            const changed = select.selectedIndex !== idx;
            select.selectedIndex = idx;
            refresh(select, wrap);
            closeSelect(wrap, { focusButton: true });
            if (changed) select.dispatchEvent(new Event('change', { bubbles: true }));
        });
        list.append(item);
    });
}

function refresh(select, wrap) {
    wrap.querySelector('.cselect__value').textContent = selectedText(select);
    wrap.hidden = select.hidden;
    wrap.classList.toggle('cselect--disabled', select.disabled);
}

function openSelect(select, wrap) {
    document.querySelectorAll(`.${OPEN_CLASS}`).forEach((other) => closeSelect(other));
    buildList(select, wrap);
    wrap.classList.add(OPEN_CLASS);
    wrap.querySelector('.cselect__button').setAttribute('aria-expanded', 'true');
    const current = wrap.querySelector('.cselect__option[aria-selected="true"]') || wrap.querySelector('.cselect__option');
    if (current) {
        current.focus();
        current.scrollIntoView({ block: 'nearest' });
    }
}

export function enhanceSelect(select) {
    if (select.dataset.enhanced) return;
    select.dataset.enhanced = 'true';

    const wrap = el('div', 'cselect');
    const button = el('button', 'cselect__button input');
    button.type = 'button';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    // o <label for=...> passa a apontar para o botão
    if (select.id) {
        button.id = `${select.id}-button`;
        document.querySelectorAll(`label[for="${select.id}"]`).forEach((label) => label.setAttribute('for', button.id));
    }
    if (select.getAttribute('aria-label')) button.setAttribute('aria-label', select.getAttribute('aria-label'));
    button.append(el('span', 'cselect__value'));
    button.insertAdjacentHTML('beforeend', iconSvg('chevron-down', 'cselect__chevron'));

    const list = el('div', 'cselect__list');
    list.setAttribute('role', 'listbox');

    select.parentNode.insertBefore(wrap, select);
    wrap.append(button, list, select);
    select.classList.add('cselect__native');
    select.tabIndex = -1;

    button.addEventListener('click', () => {
        if (wrap.classList.contains(OPEN_CLASS)) closeSelect(wrap);
        else openSelect(select, wrap);
    });

    // setas no botão fechado trocam direto; na lista aberta o foco anda entre opções
    button.addEventListener('keydown', (e) => {
        if (wrap.classList.contains(OPEN_CLASS)) return;
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            openSelect(select, wrap);
        }
    });

    // select.value = x (pelo código) atualiza o botão
    Object.defineProperty(select, 'value', {
        configurable: true,
        get() { return nativeValue.get.call(this); },
        set(v) { nativeValue.set.call(this, v); refresh(select, wrap); },
    });

    if (window.MutationObserver) {
        new MutationObserver(() => refresh(select, wrap)).observe(select, {
            childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'disabled', 'selected'],
        });
    }
    select.addEventListener('change', () => refresh(select, wrap));
    if (select.form) select.form.addEventListener('reset', () => setTimeout(() => refresh(select, wrap), 0));

    refresh(select, wrap);
}

export function enhanceSelects(root = document) {
    root.querySelectorAll('select').forEach(enhanceSelect);
}

// Clique fora ou foco saindo fecham a lista
document.addEventListener('click', (e) => {
    document.querySelectorAll(`.${OPEN_CLASS}`).forEach((wrap) => {
        if (!wrap.contains(e.target)) closeSelect(wrap);
    });
});
document.addEventListener('focusin', (e) => {
    document.querySelectorAll(`.${OPEN_CLASS}`).forEach((wrap) => {
        if (!wrap.contains(e.target)) closeSelect(wrap);
    });
});

// Esc com a lista aberta fecha só a lista (antes do modal.js e do tv-nav.js)
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    if (closeOpenSelects()) {
        e.preventDefault();
        e.stopImmediatePropagation();
    }
}, true);
