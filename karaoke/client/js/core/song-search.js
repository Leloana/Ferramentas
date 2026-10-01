// Busca de música no repertório (lista da TV e pedido pelo celular).
// Sem acento e sem diferença de maiúsculas; títulos em japonês valem também em
// romaji (title_romaji/artist_romaji de /api/songs), e espaço/pontuação não contam:
// "aoi koi daidaiiro" acha "青い、濃い、橙色の日".

// acentos latinos combinantes (U+0300–U+036F): o dakuten do japonês fica (が ≠ か)
const ACCENTS = new RegExp(`[${String.fromCharCode(0x300)}-${String.fromCharCode(0x36f)}]`, 'g');

function normalizeText(str) {
    return str ? str.normalize('NFD').replace(ACCENTS, '').toLowerCase() : '';
}

function compact(str) {
    return normalizeText(str).replace(/[\s.,;:!?'"()\[\]\-_/·、。・]+/g, '');
}

// Filtro para uma consulta: song => bool (consulta vazia aceita tudo).
export function songMatcher(query) {
    const plain = normalizeText((query || '').trim());
    const packed = compact(query);
    return (song) => {
        if (!plain) return true;
        return [song.title, song.artist, song.title_romaji, song.artist_romaji].some((f) =>
            normalizeText(f).indexOf(plain) !== -1 || (packed && compact(f).indexOf(packed) !== -1));
    };
}
