// Polyfills mínimos para navegadores de TV antigos (Chromium 68+).
// Importado primeiro no main.js. O código do app fica em ES2018: sem `?.`,
// `??` nem `catch {}`.

if (!Element.prototype.replaceChildren) {
    const replaceChildren = function (...nodes) {
        while (this.firstChild) this.removeChild(this.firstChild);
        this.append(...nodes);
    };
    Element.prototype.replaceChildren = replaceChildren;
    DocumentFragment.prototype.replaceChildren = replaceChildren;
}
