// Gabarito do cantor: marca com X os versos errados da partida gravada; o que
// tem áudio e ficou sem X é salvo como certo. Tocar numa palavra a marca com
// tempo errado (recordings/<id>/tempo_palavras.json); as cantadas longe do tempo
// da letra já vêm sublinhadas como suspeitas. Cada verso toca a voz gravada
// (com o instrumental baixinho) e mostra a transcrição inteira. Fica atrás do
// lápis discreto da tela de fim de jogo — ferramenta de calibração do score, não
// parte do jogo. Salva em recordings/<id>/gabarito.json.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { showToast } from '../core/toast.js';
import { openModal, closeModal } from '../ui/modal.js';
import { playVerse, stopReplay } from '../audio/replay.js';
import { fillWord, fillLine } from '../game/lyrics-script.js';

// Marcas antigas "cantarolei" continuam valendo como erro (o X fica aceso).
const WRONG_LABELS = ['errado', 'cantarolei'];

// Cantou a palavra mais longe que isso do tempo da letra: provável tempo errado
// (abaixo disso é o desvio normal do Whisper e do cantor).
const SUSPECT_GAP_SEC = 0.8;

function formatPrecise(sec) {
    const m = Math.floor(sec / 60);
    return `${m}:${(sec - m * 60).toFixed(1).padStart(4, '0')}`;
}

// Letra do verso palavra a palavra: tocar marca a palavra com tempo errado.
function renderWords(verse, result, marked) {
    const line = el('span', 'annotate-lyrics');
    line.append(el('span', 'annotate-num', `${verse.n}.`));
    const words = (result && result.words) || [];
    if (!words.length) {
        const lyr = el('span');
        fillLine(lyr, verse.lyrics, verse.lyrics_romaji);  // japonês: original/romaji/ambos
        line.append(document.createTextNode(' '), lyr);
        return line;
    }
    words.forEach((w, i) => {
        line.append(document.createTextNode(' '));
        const btn = el('button', 'annotate-word');
        fillWord(btn, w.word, w.romaji, '');
        btn.type = 'button';
        btn.dataset.word = String(i);
        btn.setAttribute('aria-pressed', String(marked.indexOf(i) !== -1));
        if (w.sung === null || w.sung === undefined) {
            btn.title = `letra ${formatPrecise(w.expected)} · não ouvi`;
        } else {
            btn.title = `letra ${formatPrecise(w.expected)} · cantei ${formatPrecise(w.sung)}`;
            if (Math.abs(w.sung - w.expected) > SUSPECT_GAP_SEC) btn.classList.add('is-suspect');
        }
        line.append(btn);
    });
    return line;
}

function isWrong(label) {
    return WRONG_LABELS.indexOf(label) !== -1;
}

function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

// Mostra o lápis só quando a partida foi gravada (o servidor manda o id no game_over).
export function showAnnotationButton(recordingId) {
    state.annotateRecordingId = recordingId || null;
    const btn = document.getElementById('btn-annotate-verses');
    if (btn) btn.hidden = !state.annotateRecordingId;
}

function renderList(data, player) {
    const list = document.getElementById('annotate-list');
    const labels = (data.labels && data.labels[player]) || {};
    const timing = (data.timing_marks && data.timing_marks[player]) || {};
    list.replaceChildren();
    for (const verse of data.verses) {
        const row = el('li', 'annotate-row');
        row.dataset.verse = String(verse.n);
        if (labels[verse.n]) row.dataset.label = labels[verse.n];

        const text = el('div', 'annotate-text');
        const result = verse.players[player];
        text.append(renderWords(verse, result, timing[verse.n] || []));
        const heard = el('span', 'annotate-heard', result
            ? `${formatTime(verse.start)} · nota ${Math.round(result.score)} · ouvi: `
            : `${formatTime(verse.start)} · sem áudio`);
        if (result) {
            const said = el('span');
            fillLine(said, result.heard || '—', result.heard_romaji);
            heard.append(said);
        }
        text.append(heard);

        const choices = el('div', 'annotate-choices');
        if (result) {
            const play = el('button', 'annotate-play');
            play.type = 'button';
            play.innerHTML = iconSvg('play');
            play.setAttribute('aria-label', `Ouvir o verso ${verse.n}`);
            choices.append(play);
        }
        const wrong = el('button', 'annotate-choice');
        wrong.type = 'button';
        wrong.innerHTML = iconSvg('cross');
        wrong.title = 'Errado';
        wrong.setAttribute('aria-label', `Verso ${verse.n}: errado`);
        wrong.setAttribute('aria-pressed', String(isWrong(labels[verse.n])));
        if (!result) wrong.disabled = true;
        choices.append(wrong);
        if (result) row.dataset.sung = '1';
        row.append(text, choices);
        list.append(row);
    }
    updateStatus();
}

function updateStatus() {
    const rows = document.querySelectorAll('#annotate-list .annotate-row');
    const wrong = [...rows].filter(r => isWrong(r.dataset.label)).length;
    const words = document.querySelectorAll('#annotate-list .annotate-word[aria-pressed="true"]').length;
    document.getElementById('annotate-status').textContent =
        `${wrong} ${wrong === 1 ? 'verso errado' : 'versos errados'} · ${words} ${words === 1 ? 'palavra' : 'palavras'} fora do tempo`;
}

function onPlayVerse(btn) {
    const row = btn.closest('.annotate-row');
    const data = state.annotateData;
    const verse = data.verses[Number(row.dataset.verse) - 1];
    const player = document.getElementById('annotate-player').value;
    const starting = !btn.classList.contains('is-playing');
    // o trecho cobre a letra e também onde o cantor cantou (tempo errado = fora dela)
    const sung = ((verse.players[player] || {}).words || [])
        .map(w => w.sung).filter(t => typeof t === 'number');
    playVerse({
        recordingId: state.annotateRecordingId,
        player,
        songId: data.song_id,
        start: Math.min.apply(null, [verse.start].concat(sung)),
        end: Math.max.apply(null, [verse.end || verse.start].concat(sung)),
        key: `${player}:${verse.n}`,
        button: btn,
        onStop: () => { btn.innerHTML = iconSvg('play'); },
    });
    if (starting) btn.innerHTML = iconSvg('pause');
}

// Celular: cada cantor anota os próprios versos logo depois de cantar.
export function openAnnotationFor(recordingId, player) {
    state.annotateRecordingId = recordingId;
    state.annotateOnlyPlayer = player;
    return openAnnotation();
}

async function openAnnotation() {
    const recordingId = state.annotateRecordingId;
    if (!recordingId) return;
    let data;
    try {
        const res = await fetch(`/api/recordings/${encodeURIComponent(recordingId)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        data = await res.json();
    } catch (e) {
        showToast('Não achei a gravação desta partida.', 'error');
        return;
    }
    state.annotateData = data;

    const select = document.getElementById('annotate-player');
    select.replaceChildren(...data.players.map(p => {
        const opt = el('option', null, p === 'PC_Local' ? 'Local' : p);
        opt.value = p;
        return opt;
    }));
    select.hidden = data.players.length < 2;
    const only = state.annotateOnlyPlayer;
    if (only && data.players.indexOf(only) !== -1) {
        select.value = only;
        select.hidden = true;  // no celular, só o próprio cantor
    }
    state.annotateOnlyPlayer = null;
    document.getElementById('annotate-title').textContent = data.song_title;
    // música japonesa: a mesma escolha original/romaji/ambos da letra no jogo
    const script = document.getElementById('annotate-script');
    if (script) script.hidden = !data.verses.some(v => v.lyrics_romaji);
    renderList(data, select.value);
    openModal('annotate-modal', { onClose: stopReplay });
}

async function postJson(url, body) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

async function saveAnnotation() {
    const player = document.getElementById('annotate-player').value;
    const labels = {};
    const marks = {};
    document.querySelectorAll('#annotate-list .annotate-row').forEach(row => {
        if (isWrong(row.dataset.label)) labels[row.dataset.verse] = row.dataset.label;
        else if (row.dataset.sung) labels[row.dataset.verse] = 'certo';
        const words = [...row.querySelectorAll('.annotate-word[aria-pressed="true"]')].map(b => Number(b.dataset.word));
        if (words.length) marks[row.dataset.verse] = words;
    });
    const base = `/api/recordings/${encodeURIComponent(state.annotateRecordingId)}`;
    try {
        const saved = await Promise.all([
            postJson(`${base}/gabarito`, { player, labels }),
            postJson(`${base}/tempo-palavras`, { player, marks }),
        ]);
        state.annotateData.labels = saved[0].labels;
        state.annotateData.timing_marks = saved[1].marks;
        closeModal('annotate-modal');
    } catch (e) {
        showToast('Falha ao salvar o gabarito.', 'error');
    }
}

export function initAnnotation() {
    const trigger = document.getElementById('btn-annotate-verses');
    if (!trigger) return;
    trigger.addEventListener('click', openAnnotation);
    document.getElementById('btn-annotate-close').addEventListener('click', () => closeModal('annotate-modal'));
    document.getElementById('btn-annotate-save').addEventListener('click', saveAnnotation);
    document.getElementById('annotate-player').addEventListener('change', (e) => {
        stopReplay();
        if (state.annotateData) renderList(state.annotateData, e.target.value);
    });
    // X liga/desliga o erro do verso; o play toca/para o verso.
    document.getElementById('annotate-list').addEventListener('click', (e) => {
        const play = e.target.closest('.annotate-play');
        if (play) { onPlayVerse(play); return; }
        const word = e.target.closest('.annotate-word');
        if (word) {
            word.setAttribute('aria-pressed', String(word.getAttribute('aria-pressed') !== 'true'));
            updateStatus();
            return;
        }
        const btn = e.target.closest('.annotate-choice');
        if (!btn || btn.disabled) return;
        const row = btn.closest('.annotate-row');
        const wrong = !isWrong(row.dataset.label);
        if (wrong) row.dataset.label = 'errado'; else delete row.dataset.label;
        btn.setAttribute('aria-pressed', String(wrong));
        updateStatus();
    });
}
