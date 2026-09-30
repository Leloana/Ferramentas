// Escapa texto antes de ir para innerHTML / atributos. Apelidos, títulos e
// transcrições vêm de outros usuários ou do servidor — nunca como HTML.
export function escapeHtml(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
