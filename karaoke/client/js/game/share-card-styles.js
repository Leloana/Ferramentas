// Os seis estilos de cartão que montam a própria composição (share-card.js chama
// `buildStyledCard`). Os três primeiros (caderno, neon, vidro) usam o esqueleto
// comum e só mudam no CSS; estes têm peças que não existem lá: picote e código
// de barras, linhas de cupom, disco, retícula, mosaico e plaquinhas de letreiro.
//
// A capa nunca aparece maior que o arquivo (1200 px): onde ela ocupa o cartão
// inteiro vira retícula (pôster) ou mosaico de propósito (mosaico).
// Medidas em share-card-styles.css, sempre em --u (1/100 da largura do cartão).

function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}

function shortDate() {
    const d = new Date();
    const month = d.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '').toUpperCase();
    return `${String(d.getDate()).padStart(2, '0')} ${month} ${d.getFullYear()}`;
}

function clock() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function numericDate() {
    return new Date().toLocaleDateString('pt-BR');
}

function cover(data, cls) {
    const box = el('div', `sc-cover ${cls}`);
    if (data.songId) {
        const img = el('img');
        img.alt = '';
        img.src = `/api/songs/${encodeURIComponent(data.songId)}/cover`;
        img.onerror = () => { box.classList.add('sc-cover--empty'); img.remove(); };
        box.append(img);
    } else {
        box.classList.add('sc-cover--empty');
    }
    return box;
}

function badgeText(data) {
    const rec = data.record;
    if (rec && rec.is_record && rec.times_sung > 1) return 'Recorde pessoal';
    if (rec && rec.times_sung === 1) return 'Estreia';
    return '';
}

function hasPodium(data) {
    return !!(data.podium && data.podium.length > 1);
}

function stats(data) {
    const s = data.stats || {};
    return { good: s.good || 0, ok: s.ok || 0, poor: s.poor || 0, verses: s.verses };
}

function toneOf(score) {
    if (score >= 85) return 'good';
    if (score >= 70) return 'ok';
    return 'poor';
}

// Um traço por verso, na ordem da música; sem a lista (servidor antigo), agrupa pelas contagens
function verseTones(data) {
    const s = stats(data);
    if (Array.isArray(s.verses) && s.verses.length) return s.verses.map(toneOf);
    return [].concat(Array(s.good).fill('good'), Array(s.ok).fill('ok'), Array(s.poor).fill('poor'));
}

function barcode(data, cls) {
    const bar = el('div', cls);
    verseTones(data).forEach((tone) => {
        const line = el('span');
        line.dataset.tone = tone;
        bar.append(line);
    });
    return bar;
}

function podiumList(data, cls) {
    const list = el('ol', cls);
    data.podium.slice(0, 4).forEach((p, idx) => {
        const li = el('li');
        li.append(el('span', 'sc-podium__place', `${idx + 1}º`), el('span', 'sc-podium__who', p.name),
            el('span', 'sc-podium__pts', `${Math.round(p.score)}%`));
        list.append(li);
    });
    return list;
}

function meter(data) {
    const s = stats(data);
    const bar = el('div', 'sc-meter');
    [['good', s.good], ['ok', s.ok], ['poor', s.poor]].forEach(([tone, count]) => {
        if (!count) return;
        const seg = el('span');
        seg.dataset.tone = tone;
        seg.style.flexGrow = String(count);
        bar.append(seg);
    });
    return bar;
}

function pitchText(data) {
    return typeof data.pitch === 'number' ? `${Math.round(data.pitch)}%` : '';
}

function scoreBlock(ctx, cls) {
    const box = el('div', cls);
    box.append(el('span', 'sc-score__num', String(ctx.scoreInt)), el('span', 'sc-score__pct', '%'));
    return box;
}

function field(label, value, cls) {
    const box = el('div', cls);
    box.append(el('span', 'sc-label', label), el('strong', null, value));
    return box;
}

function singerLabel(data) {
    if (hasPodium(data)) return `${data.podium.length} cantores`;
    return data.name || '–';
}

// ---------------- Ingresso: bilhete de show com canhoto picotado ----------------
function ingresso(card, data, ctx) {
    const s = stats(data);
    const main = el('div', 'sc-ticket__main');
    const head = el('header', 'sc-ticket__head');
    head.append(el('span', 'sc-ticket__brand', 'KARAOKE'), el('span', 'sc-ticket__no', `ENTRADA Nº ${String(ctx.scoreInt).padStart(4, '0')}`));
    const act = el('div', 'sc-ticket__act');
    const info = el('div', 'sc-ticket__info');
    info.append(el('span', 'sc-label sc-accent', 'ATRAÇÃO'), el('h2', 'sc-ticket__title', data.title || ''),
        el('p', 'sc-ticket__artist', data.artist || ''));
    act.append(cover(data, 'sc-ticket__cover'), info);
    const fields = el('div', 'sc-ticket__fields');
    const verses = s.good + s.ok + s.poor;
    const third = hasPodium(data) ? field('VENCEU', data.podium[0].name, 'sc-ticket__field')
        : field('VERSOS', verses ? String(verses) : '–', 'sc-ticket__field');
    fields.append(field('DATA', shortDate(), 'sc-ticket__field'), field('CANTOR', singerLabel(data), 'sc-ticket__field'), third);
    main.append(head, act, fields);
    const badge = badgeText(data);
    if (badge) main.append(el('span', 'sc-ticket__stamp', badge));

    const stub = el('div', 'sc-ticket__stub');
    const result = el('div', 'sc-ticket__result');
    const rank = el('div', 'sc-ticket__rank');
    rank.append(el('span', 'sc-ticket__rank-letter', ctx.rank.letter), el('span', 'sc-label sc-accent', ctx.rank.title.toUpperCase()));
    result.append(scoreBlock(ctx, 'sc-score sc-ticket__score'), rank);
    stub.append(result);
    if (hasPodium(data)) {
        card.classList.add('sc-ticket--podium');  // nota menor: até quatro linhas no canhoto
        stub.append(podiumList(data, 'sc-podium sc-ticket__podium'));
    } else if (verses) {
        const legend = el('div', 'sc-ticket__legend');
        legend.append(el('span', null, `${s.good} NA MOSCA`), el('span', null, `${s.ok} QUASE`),
            el('span', 'sc-accent', `${s.poor} FORA`));
        if (pitchText(data)) legend.append(el('span', 'sc-dim', `TOM ${pitchText(data)}`));
        stub.append(barcode(data, 'sc-barcode sc-ticket__barcode'), legend);
    }
    card.append(main, el('div', 'sc-ticket__perf'), stub);
}

// ---------------- Cupom: cupom fiscal de papel térmico ----------------
function receiptLine(label, value, cls) {
    const row = el('div', `sc-receipt__line${cls ? ' ' + cls : ''}`);
    row.append(el('span', null, label), el('span', null, value));
    return row;
}

function cupom(card, data, ctx) {
    const s = stats(data);
    const paper = el('div', 'sc-receipt');
    const head = el('div', 'sc-receipt__head');
    const who = el('div', 'sc-receipt__who');
    who.append(el('strong', 'sc-receipt__brand', 'KARAOKE'), el('span', null, `${numericDate()}  ${clock()}`));
    if (!hasPodium(data) && data.name) who.append(el('span', null, `CANTOR: ${data.name.toUpperCase()}`));
    head.append(cover(data, 'sc-receipt__cover'), who);
    const item = el('div', 'sc-receipt__item');
    item.append(el('strong', null, `1x ${(data.title || '').toUpperCase()}`), el('span', null, (data.artist || '').toUpperCase()));
    const lines = el('div', 'sc-receipt__lines');
    if (hasPodium(data)) {
        data.podium.slice(0, 4).forEach((p) => lines.append(receiptLine(p.name.toUpperCase(), `${Math.round(p.score)}%`)));
    } else {
        lines.append(receiptLine('VERSOS NA MOSCA', String(s.good)), receiptLine('VERSOS QUASE', String(s.ok)),
            receiptLine('VERSOS FORA', String(s.poor)));
        if (pitchText(data)) lines.append(receiptLine('TOM', pitchText(data)));
    }
    const total = el('div', 'sc-receipt__total');
    total.append(el('span', null, 'TOTAL'), el('strong', null, `${ctx.scoreInt}%`));
    const rank = receiptLine('RANK', `${ctx.rank.letter} · ${ctx.rank.title.toUpperCase()}`, 'sc-receipt__rank');
    paper.append(head, el('div', 'sc-receipt__rule'), item, lines, el('div', 'sc-receipt__rule'), total, rank);
    const badge = badgeText(data);
    if (badge) paper.append(el('p', 'sc-receipt__note', `*** ${badge.toUpperCase()} ***`));
    if (verseTones(data).length) paper.append(barcode(data, 'sc-barcode sc-receipt__barcode'));
    paper.append(el('p', 'sc-receipt__thanks', 'OBRIGADO, VOLTE SEMPRE'));
    const wrap = el('div', 'sc-receipt__wrap');
    wrap.append(paper, el('div', 'sc-receipt__tear'));
    card.append(wrap);
}

// ---------------- Vinil: a capa é a capa do disco, a nota está no selo ----------------
function legendLine(data) {
    const s = stats(data);
    const legend = el('p', 'sc-legend');
    [['good', s.good, 'na mosca'], ['ok', s.ok, 'quase'], ['poor', s.poor, 'fora']].forEach(([tone, n, txt]) => {
        const item = el('span');
        item.dataset.tone = tone;
        item.append(el('strong', null, String(n)), document.createTextNode(` ${txt}`));
        legend.append(item);
    });
    if (pitchText(data)) {
        const item = el('span');
        item.append(el('strong', null, pitchText(data)), document.createTextNode(' tom'));
        legend.append(item);
    }
    return legend;
}

function sungBy(data) {
    const by = el('span', 'sc-by');
    if (data.name) by.append(document.createTextNode('cantado por '), el('strong', null, data.name));
    return by;
}

function vinil(card, data, ctx) {
    const disc = el('div', 'sc-vinyl__disc');
    const label = el('div', 'sc-vinyl__label');
    label.append(el('span', 'sc-vinyl__label-num', String(ctx.scoreInt)), el('span', 'sc-vinyl__label-rank', `RANK ${ctx.rank.letter}`));
    disc.append(label);
    const sleeve = cover(data, 'sc-vinyl__sleeve');
    const badge = badgeText(data);
    if (badge) sleeve.append(el('span', 'sc-vinyl__sticker', badge));
    const text = el('div', 'sc-vinyl__text');
    const song = el('div', 'sc-vinyl__song');
    song.append(el('span', 'sc-label', 'LADO A · FAIXA 1'), el('h2', 'sc-vinyl__title', data.title || ''),
        el('p', 'sc-vinyl__artist', data.artist || ''));
    const foot = el('div', 'sc-vinyl__foot');
    if (hasPodium(data)) {
        foot.append(podiumList(data, 'sc-podium sc-vinyl__podium'));
    } else {
        const by = el('div', 'sc-vinyl__by');
        by.append(sungBy(data), el('span', 'sc-vinyl__rank', ctx.rank.title.toUpperCase()));
        foot.append(meter(data), legendLine(data), by);
    }
    text.append(song, foot);
    card.append(disc, sleeve, text);
}

// ---------------- Pôster: cartaz de show em retícula, a nota em letra gigante ----------------
function poster(card, data, ctx) {
    const art = el('div', 'sc-poster__art');
    art.append(cover(data, 'sc-poster__cover'), el('div', 'sc-poster__dots'));
    const top = el('div', 'sc-poster__top');
    top.append(el('span', 'sc-poster__tag', 'KARAOKE'), el('span', 'sc-poster__tag', numericDate().replace(/\//g, '.')));
    const side = el('div', 'sc-poster__side');
    side.append(el('span', 'sc-poster__pct', '%'), el('span', 'sc-poster__tag', `${ctx.rank.letter} · ${ctx.rank.title.toUpperCase()}`));
    const badge = badgeText(data);
    if (badge) side.append(el('span', 'sc-poster__tag', badge.toUpperCase()));
    const foot = el('div', 'sc-poster__foot');
    const sub = el('div', 'sc-poster__sub');
    const who = hasPodium(data)
        ? data.podium.slice(0, 3).map((p, i) => `${i + 1}º ${p.name} ${Math.round(p.score)}`).join(' · ')
        : (data.name ? `Cantado por ${data.name}` : '');
    sub.append(el('span', null, data.artist || ''), el('span', null, who));
    foot.append(el('h2', 'sc-poster__title', data.title || ''), sub);
    card.append(art, top, el('div', 'sc-poster__num', String(ctx.scoreInt)), side, foot);
}

// ---------------- Mosaico: o vidro sem esticar a capa ----------------
// O fundo é a própria capa reduzida a 12x15 quadrados (pixelada de propósito);
// a capa nítida fica no meio, no tamanho em que o arquivo aguenta.
const MOSAIC_W = 12;
const MOSAIC_H = 15;

function drawMosaic(canvas, img) {
    try {
        const w = img.naturalWidth;
        const h = img.naturalHeight;
        if (!w || !h) return;
        // recorte 4:5 do meio da capa, reduzido em dois passos (cor média, não um pixel solto)
        const sw = Math.min(w, h * 0.8);
        const sh = sw / 0.8;
        const mid = document.createElement('canvas');
        mid.width = MOSAIC_W * 4;
        mid.height = MOSAIC_H * 4;
        mid.getContext('2d').drawImage(img, (w - sw) / 2, (h - sh) / 2, sw, sh, 0, 0, mid.width, mid.height);
        canvas.getContext('2d').drawImage(mid, 0, 0, MOSAIC_W, MOSAIC_H);
        canvas.classList.add('is-ready');
    } catch (e) { /* sem canvas: fica a cor de fundo */ }
}

function mosaico(card, data, ctx) {
    const s = stats(data);
    const canvas = el('canvas', 'sc-mosaic__tiles');
    canvas.width = MOSAIC_W;
    canvas.height = MOSAIC_H;
    const front = cover(data, 'sc-mosaic__cover');
    const img = front.querySelector('img');
    if (img) {
        if (img.complete && img.naturalWidth) drawMosaic(canvas, img);
        else img.addEventListener('load', () => drawMosaic(canvas, img));
    }
    const top = el('div', 'sc-mosaic__top');
    top.append(el('span', null, 'KARAOKE'), el('span', null, shortDate()));
    const song = el('div', 'sc-mosaic__song');
    song.append(el('h2', 'sc-mosaic__title', data.title || ''), el('p', 'sc-mosaic__artist', data.artist || ''));
    const panel = el('div', 'sc-mosaic__panel');
    const result = el('div', 'sc-mosaic__result');
    const rank = el('div', 'sc-mosaic__rank');
    rank.append(el('span', 'sc-mosaic__rank-letter', ctx.rank.letter), el('span', 'sc-label', ctx.rank.title.toUpperCase()));
    result.append(scoreBlock(ctx, 'sc-score sc-mosaic__score'), rank);
    panel.append(result);
    if (hasPodium(data)) {
        panel.append(podiumList(data, 'sc-podium sc-mosaic__podium'));
    } else {
        const foot = el('div', 'sc-mosaic__foot');
        foot.append(el('span', null, `${s.good} na mosca · ${s.ok} quase · ${s.poor} fora`), sungBy(data));
        panel.append(meter(data), foot);
    }
    card.append(canvas, el('div', 'sc-mosaic__veil'), top, front, song, panel);
    const badge = badgeText(data);
    if (badge) card.append(el('span', 'sc-mosaic__badge', badge));
}

// ---------------- Letreiro: painel de aeroporto com plaquinhas ----------------
const FLAP_MIN = 14;
const FLAP_MAX = 18;

function flaps(text, cls, count) {
    const row = el('div', cls);
    const chars = Array.from(String(text || '').toUpperCase()).slice(0, count || FLAP_MAX);
    while (!count && chars.length < FLAP_MIN) chars.push(' ');
    chars.forEach((ch) => row.append(el('span', 'sc-flap', ch)));
    return row;
}

function boardRow(label, text, tone) {
    const row = el('div', 'sc-board__row');
    const tiles = flaps(text, 'sc-board__flaps');
    if (tone) tiles.dataset.tone = tone;
    row.append(el('span', 'sc-label', label), tiles);
    return row;
}

function letreiro(card, data, ctx) {
    const s = stats(data);
    const head = el('header', 'sc-board__head');
    const brand = el('div', 'sc-board__brand');
    brand.append(el('strong', null, 'KARAOKE'), el('span', 'sc-label', `PALCO · ${shortDate()} · ${clock()}`));
    head.append(brand, cover(data, 'sc-board__cover'));
    const winner = hasPodium(data) ? data.podium[0].name : data.name;
    card.append(head, boardRow('MÚSICA', data.title), boardRow('ARTISTA', data.artist));
    if (winner) card.append(boardRow(hasPodium(data) ? '1º LUGAR' : 'CANTOR', winner, 'accent'));
    const result = el('div', 'sc-board__result');
    const score = el('div', 'sc-board__col');
    score.append(el('span', 'sc-label', 'NOTA'), flaps(String(ctx.scoreInt), 'sc-board__big', 3));
    const rank = el('div', 'sc-board__col sc-board__col--rank');
    rank.append(el('span', 'sc-label', 'RANK'), flaps(ctx.rank.letter, 'sc-board__big', 1));
    result.append(score, rank);
    const foot = el('div', 'sc-board__foot');
    const detail = hasPodium(data)
        ? data.podium.slice(1, 4).map((p, i) => `${i + 2}º ${p.name.toUpperCase()} ${Math.round(p.score)}`).join(' · ')
        : `${s.good} · ${s.ok} · ${s.poor}${pitchText(data) ? ` · TOM ${pitchText(data)}` : ''}`;
    const badge = badgeText(data);
    foot.append(el('span', 'sc-board__status', (badge || ctx.rank.title).toUpperCase()), el('span', 'sc-dim', detail));
    card.append(result, foot);
}

const BUILDERS = { ingresso, cupom, vinil, poster, mosaico, letreiro };

export function hasOwnLayout(style) {
    return Object.prototype.hasOwnProperty.call(BUILDERS, style);
}

// card: o <article class="share-card"> vazio; ctx: { scoreInt, rank: {letter, title} }
export function buildStyledCard(card, style, data, ctx) {
    BUILDERS[style](card, data, ctx);
    return card;
}
