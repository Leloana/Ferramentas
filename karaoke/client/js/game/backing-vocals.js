// Voz de apoio: o que está entre parênteses na letra ("(eu sei)", o refrão do back
// vocal "(Monster)"). Aparece mais apagado e não entra na nota; verso inteiro entre
// parênteses não é pontuado (mesma regra de server/lyrics_text.py).
const OPEN = '(（';
const CLOSE = ')）';

function count(word, chars) {
    let n = 0;
    for (const c of word) if (chars.indexOf(c) >= 0) n++;
    return n;
}

// Para cada palavra: está dentro de parênteses?
export function backingFlags(words) {
    let depth = 0;
    return words.map((word) => {
        const opens = count(word, OPEN);
        const flag = depth > 0 || opens > 0;
        depth = Math.max(0, depth + opens - count(word, CLOSE));
        return flag;
    });
}

// Trechos da linha: [{ text, backing }]
export function splitBacking(text) {
    const parts = [];
    const re = /[(（][^)）]*[)）]?/g;
    let last = 0;
    let m;
    while ((m = re.exec(text || '')) !== null) {
        if (m.index > last) parts.push({ text: text.slice(last, m.index), backing: false });
        parts.push({ text: m[0], backing: true });
        last = m.index + m[0].length;
    }
    if (last < (text || '').length) parts.push({ text: text.slice(last), backing: false });
    return parts;
}

// O verso tem algo para o cantor principal?
export function hasLeadVocals(text) {
    return splitBacking(text || '').some(p => !p.backing && /[\p{L}\p{N}]/u.test(p.text));
}
