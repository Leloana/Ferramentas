// Cartão de fim de música para print (Instagram/story): formato 4:5, em três
// estilos (caderno, neon, vidro) escolhidos na barra acima do cartão. Abre por
// cima de tudo, sem botões dentro do cartão; tocar fora da barra (ou Voltar/Esc)
// fecha. No controle remoto, ←/→ trocam o estilo.
//
// Usado no fim de jogo da TV (botão da câmera) e no celular de cada cantor,
// com a nota dele. `data`:
//   { songId, title, artist, score, pitch, stats: {good, ok, poor}, name,
//     record: {is_record, best_before, times_sung}, podium: [{name, score}] }
import { iconSvg } from '../core/icons.js';
import { state } from '../core/state.js';

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

export function rankFor(score) {
    if (score >= 95) return { letter: 'S', title: 'Lendário' };
    if (score >= 85) return { letter: 'A', title: 'Excelente' };
    if (score >= 70) return { letter: 'B', title: 'Bom trabalho' };
    return { letter: 'C', title: 'Ensaio' };
}

// "Título - Artista" (formato do servidor) → { title, artist }
export function splitSongTitle(full) {
    const text = String(full || '');
    const idx = text.lastIndexOf(' - ');
    if (idx === -1) return { title: text, artist: '' };
    return { title: text.slice(0, idx), artist: text.slice(idx + 3) };
}

export const CARD_STYLES = [
    { id: 'caderno', label: 'Caderno' },
    { id: 'neon', label: 'Neon' },
    { id: 'vidro', label: 'Vidro' },
];
const STYLE_KEY = 'karaoke_card_style';

function savedStyle() {
    let id = null;
    try { id = localStorage.getItem(STYLE_KEY); } catch (e) { id = null; }
    return CARD_STYLES.some(s => s.id === id) ? id : CARD_STYLES[0].id;
}

function saveStyle(id) {
    try { localStorage.setItem(STYLE_KEY, id); } catch (e) { /* sem storage: só não lembra */ }
}

function coverUrl(songId) {
    return `/api/songs/${encodeURIComponent(songId)}/cover`;
}

function today() {
    return new Date().toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });
}

function statChip(tone, count, label) {
    const chip = el('span', 'share-chip');
    chip.dataset.tone = tone;
    chip.append(el('strong', null, String(count)), el('span', null, label));
    return chip;
}

export function buildShareCard(data, style) {
    const score = Math.max(0, Math.min(100, parseFloat(data.score) || 0));
    const rank = rankFor(score);

    const card = el('article', 'share-card');
    card.dataset.rank = rank.letter;
    card.dataset.style = style || CARD_STYLES[0].id;

    // fundo do estilo vidro: a capa ampliada e desfocada (os outros estilos escondem)
    const backdrop = el('div', 'share-card__backdrop');
    if (data.songId) {
        const blur = el('img');
        blur.alt = '';
        blur.src = coverUrl(data.songId);
        blur.onerror = () => blur.remove();
        backdrop.append(blur);
    }
    card.append(backdrop);

    const top = el('header', 'share-card__top');
    const brand = el('span', 'share-card__brand');
    const logo = el('img');
    logo.src = '/assets/art/logo-mark.svg';
    logo.alt = '';
    brand.append(logo, el('span', null, 'Karaoke'));
    top.append(brand, el('span', 'share-card__date', today()));
    card.append(top);

    const photo = el('figure', 'share-card__photo');
    if (data.songId) {
        const img = el('img', 'share-card__cover');
        img.alt = '';
        img.src = coverUrl(data.songId);
        img.onerror = () => { photo.classList.add('share-card__photo--empty'); img.remove(); };
        photo.append(img);
    } else {
        photo.classList.add('share-card__photo--empty');
    }
    photo.insertAdjacentHTML('beforeend', iconSvg('note', 'share-card__photo-icon'));
    if (data.record && data.record.is_record && data.record.times_sung > 1) {
        photo.append(el('span', 'share-card__stamp', 'Recorde pessoal'));
    } else if (data.record && data.record.times_sung === 1) {
        photo.append(el('span', 'share-card__stamp share-card__stamp--first', 'Estreia'));
    }
    card.append(photo);

    const song = el('div', 'share-card__song');
    song.append(el('h2', 'share-card__title', data.title || ''), el('p', 'share-card__artist', data.artist || ''));
    card.append(song);

    const scoreRow = el('div', 'share-card__score-row');
    const big = el('div', 'share-card__score');
    big.append(el('span', 'share-card__score-num', String(Math.round(score))), el('span', 'share-card__score-pct', '%'));
    const rankBox = el('div', 'share-card__rank');
    rankBox.append(el('span', 'share-card__rank-letter', rank.letter), el('span', 'share-card__rank-title', rank.title));
    scoreRow.append(big, rankBox);
    card.append(scoreRow);

    const chips = el('div', 'share-card__chips');
    if (data.stats) {
        chips.append(
            statChip('good', data.stats.good || 0, 'na mosca'),
            statChip('ok', data.stats.ok || 0, 'quase'),
            statChip('poor', data.stats.poor || 0, 'fora'),
        );
    }
    if (typeof data.pitch === 'number') chips.append(statChip('pitch', `${Math.round(data.pitch)}%`, 'tom'));
    if (chips.childNodes.length) card.append(chips);

    if (data.podium && data.podium.length > 1) {
        const podium = el('ol', 'share-card__podium');
        data.podium.slice(0, 4).forEach((p, idx) => {
            const li = el('li');
            li.append(el('span', 'share-card__place', `${idx + 1}º`), el('span', 'share-card__who', p.name),
                el('span', 'share-card__pts', `${Math.round(p.score)}%`));
            podium.append(li);
        });
        card.append(podium);
    } else if (data.name) {
        const by = el('p', 'share-card__by');
        by.append(el('span', null, 'cantado por '), el('strong', null, data.name));
        card.append(by);
    }

    return card;
}

export function closeShareCard() {
    const overlay = document.getElementById('share-card-overlay');
    if (overlay) overlay.remove();
    document.documentElement.classList.remove('share-card-open');
    window.removeEventListener('keydown', onKey, true);
    // controle remoto: o foco volta para onde estava (o botão Cartão)
    const back = state.shareCardReturnFocus;
    state.shareCardReturnFocus = null;
    if (overlay && back && document.body.contains(back)) back.focus();
}

// Controle remoto: OK/Enter e as teclas de voltar (Android/Google TV, Tizen,
// webOS) fecham; setas não vazam para a tela de fim de jogo escondida atrás.
// No TV Bro o Voltar nem chega à página — o OK era a única saída e não fechava.
const CLOSE_KEYS = ['Escape', 'Esc', 'Backspace', 'BrowserBack', 'GoBack', 'Enter', ' '];
const CLOSE_CODES = [10009, 461, 13, 32];
const ARROW_KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Up', 'Down', 'Left', 'Right'];

const PREV_KEYS = ['ArrowLeft', 'Left'];
const NEXT_KEYS = ['ArrowRight', 'Right'];

function onKey(e) {
    const close = CLOSE_KEYS.indexOf(e.key) !== -1 || CLOSE_CODES.indexOf(e.keyCode) !== -1;
    if (!close && ARROW_KEYS.indexOf(e.key) === -1) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (close) { closeShareCard(); return; }
    const step = PREV_KEYS.indexOf(e.key) !== -1 ? -1 : NEXT_KEYS.indexOf(e.key) !== -1 ? 1 : 0;
    if (step) {
        const ids = CARD_STYLES.map(st => st.id);
        const card = document.querySelector('#share-card-overlay .share-card');
        const at = ids.indexOf(card ? card.dataset.style : ids[0]);
        setCardStyle(ids[(at + step + ids.length) % ids.length]);
    }
}

function setCardStyle(id) {
    const overlay = document.getElementById('share-card-overlay');
    if (!overlay) return;
    const card = overlay.querySelector('.share-card');
    if (card) card.dataset.style = id;
    overlay.dataset.style = id;
    overlay.querySelectorAll('.share-card-style').forEach(btn => {
        btn.setAttribute('aria-checked', String(btn.dataset.style === id));
    });
    saveStyle(id);
}

function styleBar() {
    const bar = el('div', 'share-card-bar');
    bar.setAttribute('role', 'radiogroup');
    bar.setAttribute('aria-label', 'Estilo do cartão');
    CARD_STYLES.forEach(({ id, label }) => {
        const btn = el('button', 'btn btn--sm share-card-style', label);
        btn.type = 'button';
        btn.dataset.style = id;
        btn.setAttribute('role', 'radio');
        btn.addEventListener('click', () => setCardStyle(id));
        bar.append(btn);
    });
    // tocar na barra troca o estilo, não fecha o cartão
    bar.addEventListener('click', (e) => e.stopPropagation());
    return bar;
}

export function openShareCard(data) {
    closeShareCard();
    state.shareCardReturnFocus = document.activeElement;
    const overlay = el('div', 'share-card-overlay');
    overlay.id = 'share-card-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', 'Cartão da música');
    overlay.tabIndex = -1;
    const style = savedStyle();
    overlay.append(styleBar(), buildShareCard(data, style));
    // TV: botão visível (share-card.css só mostra com html.is-tv)
    const closeBtn = el('button', 'btn share-card-close');
    closeBtn.type = 'button';
    closeBtn.innerHTML = iconSvg('close');
    closeBtn.append(document.createTextNode(' Fechar'));
    overlay.append(closeBtn);
    // tocar em qualquer lugar fecha (o print é pelo botão do aparelho)
    overlay.addEventListener('click', closeShareCard);
    document.body.append(overlay);
    setCardStyle(style);
    // esconde a página por trás: no TV Bro o cartão aparecia atrás do fim de jogo
    // na 1ª vez (camadas da GPU furavam o z-index)
    document.documentElement.classList.add('share-card-open');
    window.addEventListener('keydown', onKey, true);  // antes do tv-nav (document)
    overlay.focus();
}
