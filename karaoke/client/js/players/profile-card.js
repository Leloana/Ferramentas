// Cartão do perfil (botão "Card" na aba Perfil do celular): o mesmo cartão 4:5
// do fim de jogo, nos mesmos nove estilos, com o cantor no lugar da música —
// foto (ou a capa da melhor música), média como nota, melhores músicas no pódio.
// "Baixar" desenha o cartão em 1080x1350 com o html2canvas (js/vendor, carregado
// só na hora) e abre o compartilhar do celular ou baixa o PNG.
import { openModal } from '../ui/modal.js';
import { showToast } from '../core/toast.js';
import { avatarUrl } from './avatar.js';
import { buildShareCard, mountShareCards } from '../game/share-card.js';

const EXPORT_U = 10.8;  // px por --u: cartão de 1080x1350
const H2C_URL = '/js/vendor/html2canvas.min.js';

function pct(v) {
    return typeof v === 'number' ? `${Math.round(v)}%` : '—';
}

// /api/players/<apelido> → dados do cartão (formato de share-card.js)
export function profileCardData(detail) {
    const records = detail.records || [];
    const games = detail.games || 0;
    const top = records[0];
    // o recorde já é o 1º da lista de músicas
    const extras = [];
    if (typeof detail.avg_pitch === 'number') extras.push({ label: 'Afinação', value: pct(detail.avg_pitch) });
    return {
        kind: 'profile',
        title: detail.name,
        artist: `${games} ${games === 1 ? 'música' : 'músicas'}`,
        games: String(games),
        best: pct(detail.best),
        score: detail.avg || 0,
        pitch: typeof detail.avg_pitch === 'number' ? detail.avg_pitch : undefined,
        // sem foto: a capa da melhor música
        coverUrl: detail.avatar ? avatarUrl(detail.name, detail.avatar) : null,
        songId: !detail.avatar && top ? top.song_id : null,
        podium: records.slice(0, 4).map((r) => ({ name: r.name || r.song_id, score: r.best })),
        extras,
        name: null,
    };
}

function loadHtml2canvas() {
    if (window.html2canvas) return Promise.resolve(window.html2canvas);
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = H2C_URL;
        script.onload = () => resolve(window.html2canvas);
        script.onerror = () => reject(new Error('Não deu para gerar a imagem'));
        document.head.append(script);
    });
}

function imagesReady(root) {
    const imgs = Array.from(root.querySelectorAll('img'));
    return Promise.all(imgs.map((img) => (img.complete ? null : new Promise((done) => {
        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', done, { once: true });
    }))));
}

// SVG em <img> (logo) sai vazio no html2canvas: vira PNG antes de desenhar
async function rasterizeSvgs(root) {
    const imgs = Array.from(root.querySelectorAll('img')).filter((img) => /\.svg(\?|$)/.test(img.currentSrc || img.src));
    await Promise.all(imgs.map((img) => {
        const w = img.offsetWidth;
        const h = img.offsetHeight;
        if (!w || !h) return null;
        const canvas = document.createElement('canvas');
        canvas.width = w * 2;
        canvas.height = h * 2;
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        return new Promise((done) => {
            img.onload = done;
            img.onerror = done;
            img.src = canvas.toDataURL('image/png');
        });
    }));
}

// Mosaico: o canvas de 12x15 é ampliado sem suavizar (no CSS é image-rendering: pixelated)
function pixelateMosaic(doc) {
    doc.querySelectorAll('canvas.sc-mosaic__tiles').forEach((small) => {
        const cs = doc.defaultView.getComputedStyle(small);
        const big = doc.createElement('canvas');
        big.className = small.className;
        big.width = parseFloat(cs.width) || small.width;
        big.height = parseFloat(cs.height) || small.height;
        const ctx = big.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(small, 0, 0, big.width, big.height);
        small.replaceWith(big);
    });
}

// html2canvas não entende object-fit: a capa vira fundo "cover" na cópia desenhada
function coverImagesAsBackground(doc) {
    doc.querySelectorAll('.share-card img').forEach((img) => {
        const fit = doc.defaultView.getComputedStyle(img).objectFit;
        if (fit !== 'cover' || !img.currentSrc) return;
        const box = doc.createElement('div');
        box.className = img.className;
        box.style.cssText = img.style.cssText;
        const cs = doc.defaultView.getComputedStyle(img);
        ['position', 'top', 'left', 'right', 'bottom', 'width', 'height', 'display', 'border', 'borderRadius', 'boxShadow', 'transform']
            .forEach((k) => { box.style[k] = cs[k]; });
        box.style.backgroundImage = `url("${img.currentSrc}")`;
        box.style.backgroundSize = 'cover';
        box.style.backgroundPosition = 'center';
        img.replaceWith(box);
    });
}

async function cardImage(data, style) {
    const h2c = await loadHtml2canvas();
    // cópia fora da tela no tamanho final (as medidas são todas em --u)
    const stage = document.createElement('div');
    stage.className = 'share-card-frame profile-card-export';
    stage.style.setProperty('--u', `${EXPORT_U}px`);
    const card = buildShareCard(data, style);
    card.style.boxShadow = 'none';
    stage.append(card);
    document.body.append(stage);
    try {
        await imagesReady(stage);
        if (document.fonts && document.fonts.ready) await document.fonts.ready;
        await new Promise((r) => setTimeout(r, 120));  // mosaico desenha no load da capa
        await rasterizeSvgs(card);
        const canvas = await h2c(card, {
            scale: 1,
            backgroundColor: null,
            useCORS: true,
            logging: false,
            onclone: (doc) => {
                coverImagesAsBackground(doc);
                pixelateMosaic(doc);
            },
        });
        return await new Promise((resolve, reject) => {
            canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Não deu para gerar a imagem'))), 'image/png');
        });
    } finally {
        stage.remove();
    }
}

function fileName(name) {
    const slug = String(name || 'perfil').normalize('NFD').replace(/[̀-ͯ]/g, '')
        .replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase();
    return `karaoke-${slug || 'perfil'}.png`;
}

// Celular: folha de compartilhar (salvar na galeria, mandar no WhatsApp); senão baixa
async function saveImage(blob, name) {
    const file = typeof File === 'function' ? new File([blob], name, { type: 'image/png' }) : null;
    if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
            await navigator.share({ files: [file] });
            return;
        } catch (e) {
            if (e && e.name === 'AbortError') return;  // fechou a folha: nada a fazer
        }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function openProfileCard(detail) {
    const modal = document.getElementById('profile-card-modal');
    const view = document.getElementById('profile-card-view');
    const styles = document.getElementById('profile-card-styles');
    const download = document.getElementById('btn-profile-card-download');
    if (!modal || !view || !detail) return;
    const data = profileCardData(detail);
    mountShareCards(view, [data], styles);
    openModal(modal);
    download.onclick = async () => {
        const shown = view.querySelector('.share-card');
        download.disabled = true;
        try {
            await saveImage(await cardImage(data, shown ? shown.dataset.style : undefined), fileName(detail.name));
        } catch (e) {
            showToast(e.message || 'Não deu para gerar a imagem', 'error');
        } finally {
            download.disabled = false;
        }
    };
}
