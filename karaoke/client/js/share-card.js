// Cartão de fim de música para print (Instagram/story): formato 4:5, estilo
// partitura antiga. Abre por cima de tudo, sem botões dentro do cartão; tocar
// em qualquer lugar (ou Voltar/Esc) fecha.
//
// Usado no fim de jogo da TV (botão da câmera) e no celular de cada cantor,
// com a nota dele. `data`:
//   { songId, title, artist, score, pitch, stats: {good, ok, poor}, name,
//     record: {is_record, best_before, times_sung}, podium: [{name, score}] }
import { iconSvg } from './icons.js';

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

function today() {
    return new Date().toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });
}

function statChip(tone, count, label) {
    const chip = el('span', 'share-chip');
    chip.dataset.tone = tone;
    chip.append(el('strong', null, String(count)), el('span', null, label));
    return chip;
}

export function buildShareCard(data) {
    const score = Math.max(0, Math.min(100, parseFloat(data.score) || 0));
    const rank = rankFor(score);

    const card = el('article', 'share-card');
    card.dataset.rank = rank.letter;

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
        img.src = `/api/songs/${encodeURIComponent(data.songId)}/cover`;
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

    const foot = el('footer', 'share-card__foot');
    foot.insertAdjacentHTML('beforeend', '<img src="/assets/art/staff-divider.svg" alt="">');
    card.append(foot);
    return card;
}

export function closeShareCard() {
    const overlay = document.getElementById('share-card-overlay');
    if (overlay) overlay.remove();
    document.removeEventListener('keydown', onKey, true);
}

function onKey(e) {
    if (e.key === 'Escape' || e.key === 'Esc' || e.key === 'Backspace' || e.keyCode === 10009 || e.keyCode === 461) {
        e.preventDefault();
        e.stopImmediatePropagation();
        closeShareCard();
    }
}

export function openShareCard(data) {
    closeShareCard();
    const overlay = el('div', 'share-card-overlay');
    overlay.id = 'share-card-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', 'Cartão da música');
    overlay.tabIndex = -1;
    overlay.append(buildShareCard(data));
    // tocar em qualquer lugar fecha (o print é pelo botão do aparelho)
    overlay.addEventListener('click', closeShareCard);
    document.body.append(overlay);
    document.addEventListener('keydown', onKey, true);
    overlay.focus();
}
