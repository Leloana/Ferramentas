// Cartão de fim de música para print (Instagram/story): formato 4:5, em nove
// estilos escolhidos na barra acima do cartão (na TV, na lista ao lado). A capa ocupa
// o alto, com o nome da música por cima; embaixo ficam a nota, o rank e a barra de
// acertos. Cada estilo muda a composição, não só as cores. Abre por cima de tudo,
// sem botões dentro do cartão; tocar fora da barra (ou Voltar/Esc) fecha. No
// controle remoto, as setas trocam o estilo. Caderno, neon e vidro dividem o
// esqueleto daqui; os outros montam o próprio (share-card-styles.js).
//
// Usado no fim de jogo da TV (botão da câmera) e no celular de cada cantor,
// com a nota dele. `data`:
//   { songId, title, artist, score, pitch, stats: {good, ok, poor}, name,
//     record: {is_record, best_before, times_sung}, podium: [{name, score}] }
// `stats.verses` (nota de cada verso, na ordem) desenha o código de barras.
import { iconSvg } from '../core/icons.js';
import { state } from '../core/state.js';
import { buildStyledCard, hasOwnLayout } from './share-card-styles.js';

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
    { id: 'ingresso', label: 'Ingresso' },
    { id: 'cupom', label: 'Cupom' },
    { id: 'vinil', label: 'Vinil' },
    { id: 'poster', label: 'Pôster' },
    { id: 'mosaico', label: 'Mosaico' },
    { id: 'letreiro', label: 'Letreiro' },
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

// Barra de acertos: um trecho por faixa, do tamanho da contagem
function meter(stats) {
    const bar = el('div', 'share-card__meter');
    [['good', stats.good], ['ok', stats.ok], ['poor', stats.poor]].forEach(([tone, count]) => {
        if (!count) return;
        const seg = el('span', 'share-card__seg');
        seg.dataset.tone = tone;
        seg.style.flexGrow = String(count);
        bar.append(seg);
    });
    return bar;
}

function legendItem(tone, value, label) {
    const item = el('span', 'share-card__legend-item');
    item.dataset.tone = tone;
    item.append(el('strong', null, String(value)), document.createTextNode(` ${label}`));
    return item;
}

// Arte: a capa ocupa o alto do cartão, com marca, data, selo e o nome da música por cima
function artBlock(data) {
    const art = el('div', 'share-card__art');
    if (data.songId) {
        const img = el('img', 'share-card__cover');
        img.alt = '';
        img.src = coverUrl(data.songId);
        img.onerror = () => { art.classList.add('share-card__art--empty'); img.remove(); };
        art.append(img);
    } else {
        art.classList.add('share-card__art--empty');
    }
    art.insertAdjacentHTML('beforeend', iconSvg('note', 'share-card__art-icon'));
    art.append(el('div', 'share-card__shade'));

    const top = el('header', 'share-card__top');
    const brand = el('span', 'share-card__brand');
    const logo = el('img');
    logo.src = '/assets/art/logo-mark.svg';
    logo.alt = '';
    brand.append(logo, el('span', null, 'Karaoke'));
    top.append(brand, el('span', 'share-card__date', today()));
    art.append(top);

    if (data.record && data.record.is_record && data.record.times_sung > 1) {
        art.append(el('span', 'share-card__badge', 'Recorde pessoal'));
    } else if (data.record && data.record.times_sung === 1) {
        art.append(el('span', 'share-card__badge share-card__badge--first', 'Estreia'));
    }

    const song = el('div', 'share-card__song');
    song.append(el('h2', 'share-card__title', data.title || ''), el('p', 'share-card__artist', data.artist || ''));
    art.append(song);
    return art;
}

export function buildShareCard(data, style) {
    const score = Math.max(0, Math.min(100, parseFloat(data.score) || 0));
    const rank = rankFor(score);

    const card = el('article', 'share-card');
    card.dataset.rank = rank.letter;
    card.dataset.style = style || CARD_STYLES[0].id;
    if (hasOwnLayout(card.dataset.style)) {
        return buildStyledCard(card, card.dataset.style, data, { scoreInt: Math.round(score), rank });
    }
    // pódio: quatro linhas a mais, a foto e a nota diminuem (share-card--podium)
    if (data.podium && data.podium.length > 1) card.classList.add('share-card--podium');
    card.append(artBlock(data));

    const body = el('section', 'share-card__body');
    const result = el('div', 'share-card__result');
    const big = el('div', 'share-card__score');
    big.append(el('span', 'share-card__score-num', String(Math.round(score))), el('span', 'share-card__score-pct', '%'));
    const rankBox = el('div', 'share-card__rank');
    rankBox.append(el('span', 'share-card__rank-letter', rank.letter), el('span', 'share-card__rank-title', rank.title));
    result.append(big, rankBox);
    body.append(result);

    // com pódio a barra de acertos sai: as notas são de vários cantores e não cabem as duas
    const podiumRows = data.podium && data.podium.length > 1;
    const hasPitch = typeof data.pitch === 'number' && !podiumRows;
    if ((data.stats && !podiumRows) || hasPitch) {
        const withStats = data.stats && !podiumRows;
        if (withStats) body.append(meter(data.stats));
        const legend = el('p', 'share-card__legend');
        if (withStats) {
            legend.append(
                legendItem('good', data.stats.good || 0, 'na mosca'),
                legendItem('ok', data.stats.ok || 0, 'quase'),
                legendItem('poor', data.stats.poor || 0, 'fora'),
            );
        }
        if (hasPitch) legend.append(legendItem('pitch', `${Math.round(data.pitch)}%`, 'tom'));
        body.append(legend);
    }

    if (podiumRows) {
        const podium = el('ol', 'share-card__podium');
        data.podium.slice(0, 4).forEach((p, idx) => {
            const li = el('li');
            li.append(el('span', 'share-card__place', `${idx + 1}º`), el('span', 'share-card__who', p.name),
                el('span', 'share-card__pts', `${Math.round(p.score)}%`));
            podium.append(li);
        });
        body.append(podium);
    } else if (data.name) {
        const by = el('p', 'share-card__by');
        by.append(el('span', null, 'cantado por '), el('strong', null, data.name));
        body.append(by);
    }

    card.append(body);
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
    state.shareCardData = null;
    if (overlay && back && document.body.contains(back)) back.focus();
}

// Controle remoto: OK/Enter e as teclas de voltar (Android/Google TV, Tizen,
// webOS) fecham; setas não vazam para a tela de fim de jogo escondida atrás.
// No TV Bro o Voltar nem chega à página — o OK era a única saída e não fechava.
const CLOSE_KEYS = ['Escape', 'Esc', 'Backspace', 'BrowserBack', 'GoBack', 'Enter', ' '];
const CLOSE_CODES = [10009, 461, 13, 32];
const ARROW_KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Up', 'Down', 'Left', 'Right'];

const PREV_KEYS = ['ArrowLeft', 'Left', 'ArrowUp', 'Up'];
const NEXT_KEYS = ['ArrowRight', 'Right', 'ArrowDown', 'Down'];

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
    // cada estilo tem a própria composição: o cartão é montado de novo
    const card = overlay.querySelector('.share-card');
    if (card && state.shareCardData) card.replaceWith(buildShareCard(state.shareCardData, id));
    else if (card) card.dataset.style = id;
    overlay.dataset.style = id;
    overlay.querySelectorAll('.share-card-style').forEach(btn => {
        const on = btn.dataset.style === id;
        btn.setAttribute('aria-checked', String(on));
        // celular: a barra rola de lado, o estilo escolhido fica à vista
        const bar = btn.parentNode;
        if (on && bar.scrollWidth > bar.clientWidth) {
            bar.scrollLeft = btn.offsetLeft - (bar.clientWidth - btn.offsetWidth) / 2;
        }
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
    state.shareCardData = data;
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
