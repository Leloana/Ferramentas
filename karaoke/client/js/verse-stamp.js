// Carimbo de ensaio: retorno de acerto/erro de cada verso.
//
// A nota do verso vira uma palavra curta com a cor pastel da faixa
// (Afinado · Quase · Fora). Usado no palco (solo), nas barras de placar
// (multiplayer) e na nota do celular-microfone.

const LEVELS = [
    { min: 85, key: 'good', word: 'Afinado' },
    { min: 70, key: 'ok', word: 'Quase' },
    { min: -Infinity, key: 'poor', word: 'Fora' },
];

export function verseQuality(score) {
    const value = parseFloat(score) || 0;
    for (let i = 0; i < LEVELS.length; i++) {
        if (value >= LEVELS[i].min) return LEVELS[i];
    }
    return LEVELS[LEVELS.length - 1];
}

// Reinicia uma animação CSS (a mesma classe duas vezes seguidas não repete sozinha).
export function replayClass(node, cls) {
    node.classList.remove(cls);
    void node.offsetWidth;
    node.classList.add(cls);
}

// Bate o carimbo em `stamp` (.verse-stamp com __word e __score) e o recolhe
// depois de `holdMs`. O timeout fica no próprio elemento.
export function stampVerse(stamp, score, holdMs) {
    if (!stamp) return;
    const q = verseQuality(score);
    const word = stamp.querySelector('.verse-stamp__word');
    const num = stamp.querySelector('.verse-stamp__score');
    if (word) word.textContent = q.word;
    if (num) num.textContent = `${Math.round(parseFloat(score) || 0)}%`;
    stamp.dataset.quality = q.key;
    stamp.classList.remove('verse-stamp--out');
    replayClass(stamp, 'verse-stamp--in');

    clearTimeout(stamp.stampTimer);
    stamp.stampTimer = setTimeout(() => {
        stamp.classList.remove('verse-stamp--in');
        stamp.classList.add('verse-stamp--out');
    }, holdMs || 1800);
}

export function clearStamp(stamp) {
    if (!stamp) return;
    clearTimeout(stamp.stampTimer);
    stamp.classList.remove('verse-stamp--in', 'verse-stamp--out');
    delete stamp.dataset.quality;
}
