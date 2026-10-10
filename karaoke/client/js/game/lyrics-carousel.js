// Carrossel da letra na TV: quatro linhas (anterior, atual, próxima, depois) que
// deslizam um verso para cima a cada troca, com a atual centrada no palco.
import { state } from '../core/state.js';
import { dom } from '../core/dom.js';
import { isTvBrowser } from '../core/config.js';
import { fillLine, fillWord, setLyricsScriptAvailable } from './lyrics-script.js';
import { fitLongVerse } from './long-verse.js';
import { backingFlags } from './backing-vocals.js';

const SLIDE_MS = 400;

// Linha que passa a conter spans de palavra: deixa de ser redesenhada como linha
// inteira quando o modo de escrita (original/romaji/ambos) muda.
function clearLine(el) {
    el.classList.remove('lyrics-line');
    delete el.dataset.original;
    delete el.dataset.romaji;
    el.innerHTML = '';
}

// Japonês em kanji/kana não separa palavras com espaço; letra em romaji e trechos
// em inglês separam (espelha separator_between em server/lyrics_text.py).
const JA_SCRIPT_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u3005]/; // kana + kanji + 々
function wordSeparator(language, word, nextWord) {
    const japanese = (language || '').toLowerCase().startsWith('ja');
    if (japanese && JA_SCRIPT_RE.test(word) && (!nextWord || JA_SCRIPT_RE.test(nextWord))) return '';
    return ' ';
}

// Linha do verso: inteira no modo "verso", palavra por palavra (#word-N) no modo "palavra"
function fillVerseLine(el, data) {
    if (state.syncMode === 'verse') {
        fillLine(el, data.lyrics, data.lyrics_romaji);
        return;
    }
    clearLine(el);
    const backing = backingFlags(data.lyrics_timed.map(item => item.word));
    data.lyrics_timed.forEach((item, idx) => {
        const span = document.createElement('span');
        span.className = backing[idx] ? 'word lyrics-backing' : 'word';
        fillWord(span, item.word, item.romaji, wordSeparator(data.language, item.word, (data.lyrics_timed[idx + 1] || {}).word));
        span.id = `word-${idx}`;
        el.appendChild(span);
    });
}

function carouselInner() {
    return document.getElementById('carousel-inner');
}

function getTranslationForLine(line) {
    const container = document.querySelector('.carousel-container');
    const inner = carouselInner();
    if (!container || !inner || !line) return 0;

    // Posição real na tela, não offsetTop: o carousel-inner é mais alto que o palco
    // e transborda centralizado, e a conta por offsetTop errava conforme a altura das
    // linhas (na TV a letra subia demais e descia de volta a cada verso).
    // Novo deslocamento = deslocamento atual (mesmo no meio de uma transição) + o
    // que falta para o centro da linha chegar ao centro do palco.
    const box = container.getBoundingClientRect();
    const rect = line.getBoundingClientRect();
    // --stage-anchor (states.css): onde fica a linha atual no palco, 0.5 = no meio.
    // Com vários cantores o palco é baixo e ela sobe, para a próxima caber embaixo.
    const anchor = parseFloat(getComputedStyle(container).getPropertyValue('--stage-anchor')) || 0.5;
    const stageCenter = box.top + container.clientTop + container.clientHeight * anchor;
    // verso alto (várias linhas) não passa do topo do palco: o começo dele é o que se canta
    const stageTop = box.top + container.clientTop + (parseFloat(getComputedStyle(container).paddingTop) || 0);
    const lineTop = Math.max(stageCenter - rect.height / 2, stageTop);
    return currentTranslateY(inner) + (lineTop - rect.top);
}

// translateY em vigor agora (a matriz calculada já reflete a transição em curso).
function currentTranslateY(el) {
    const t = getComputedStyle(el).transform;
    if (!t || t === 'none') return 0;
    const nums = t.slice(t.indexOf('(') + 1, -1).split(',').map(parseFloat);
    if (t.indexOf('matrix3d') === 0) return nums[13] || 0;
    return nums[5] || 0;
}

// Centraliza a linha sem animação
function snapTo(inner, line) {
    inner.classList.add('no-transition');
    if (line) inner.style.transform = `translateY(${getTranslationForLine(line)}px)`;
    inner.offsetHeight; // força o reflow
    inner.classList.remove('no-transition');
}

// Mantém a linha atual centrada quando a janela muda de tamanho
window.addEventListener('resize', () => {
    if (state.isSingingActive || (state.currentSegmentData && state.currentAppState !== 'idle')) {
        const inner = carouselInner();
        fitLongVerse(dom.lyricsDisplay);
        if (inner) snapTo(inner, state.slideTransitionCleanup ? dom.nextLyricsDisplay : dom.lyricsDisplay);
    }
});

export function renderLyrics(data) {
    setLyricsScriptAvailable(data.lyrics_romaji);
    const virtualTime = dom.audioPlayer.currentTime + state.syncOffset;
    const pauseTime = data.sing_start - virtualTime;

    if (pauseTime > 3.0) {
        state.totalPauseDuration = pauseTime;
        state.pauseStartTarget = data.sing_start;
    } else {
        state.totalPauseDuration = 0;
        state.pauseStartTarget = 0;
    }

    if (state.isFirstSegment) {
        state.isFirstSegment = false;
        state.lastSegmentLyricsTimed = null;
        state.currentSegmentData = data;
        updateLyricsDOM(data);
        const inner = carouselInner();
        if (inner) snapTo(inner, dom.lyricsDisplay);
        return;
    }

    // Resolve a transição anterior na hora para não sobrepor
    if (state.slideTransitionCleanup) {
        state.slideTransitionCleanup();
    }

    // Estado novo já agora: o laço da letra passa a usar os tempos do verso novo
    const oldSegmentData = state.currentSegmentData;
    state.lastSegmentLyricsTimed = oldSegmentData ? oldSegmentData.lyrics_timed : null;
    state.currentSegmentData = data;

    const linePrev = dom.prevLyricsDisplay;
    const lineCurr = dom.lyricsDisplay;
    const lineNext = dom.nextLyricsDisplay;
    const lineUpcoming = dom.upcomingLyricsDisplay;
    const inner = carouselInner();

    if (!inner) {
        updateLyricsDOM(data);
        return;
    }

    // Tira os IDs das palavras da linha atual: o verso novo usa os mesmos #word-N
    lineCurr.querySelectorAll('.word').forEach(span => span.removeAttribute('id'));

    fillVerseLine(lineNext, data);
    if (lineUpcoming) {
        fillLine(lineUpcoming, data.next_lyrics, data.next_lyrics_romaji);
    }

    const addSlideClasses = () => {
        linePrev.classList.add('line-prev-slide-out');
        lineCurr.classList.add('line-curr-to-prev');
        lineNext.classList.add('line-next-to-curr');
        if (lineUpcoming) {
            lineUpcoming.classList.add('line-upcoming-to-next');
        }
    };

    if (isTvBrowser) {
        // TV: o tamanho da fonte muda sem animação (tv.css). Mede o centro já com a
        // próxima linha grande; medida antes, a letra subia demais e depois descia.
        addSlideClasses();
        inner.offsetHeight; // força o layout com os tamanhos novos
        inner.style.transform = `translateY(${getTranslationForLine(lineNext)}px)`;
    } else {
        inner.style.transform = `translateY(${getTranslationForLine(lineNext)}px)`;
        addSlideClasses();
    }

    // Fim do deslize: troca o conteúdo das linhas e volta tudo para o lugar
    const commitTransition = () => {
        inner.classList.add('no-transition');

        fillLine(linePrev, data.prev_lyrics, data.prev_lyrics_romaji);
        if (state.syncMode === 'verse') {
            fillLine(lineCurr, lineNext.dataset.original, lineNext.dataset.romaji);
        } else {
            clearLine(lineCurr);
            lineCurr.innerHTML = lineNext.innerHTML;
        }
        fillLine(lineNext, data.next_lyrics, data.next_lyrics_romaji);
        if (lineUpcoming) {
            fillLine(lineUpcoming, data.upcoming_lyrics, data.upcoming_lyrics_romaji);
        }

        // Tira as classes de transição ANTES de medir: medida com elas, a nova linha
        // atual ainda estava no tamanho de "anterior" e a letra pulava depois.
        linePrev.classList.remove('line-prev-slide-out');
        lineCurr.classList.remove('line-curr-to-prev');
        lineNext.classList.remove('line-next-to-curr');
        if (lineUpcoming) {
            lineUpcoming.classList.remove('line-upcoming-to-next');
        }
        fitLongVerse(lineCurr);  // verso comprido: encolhe ou vira janela que rola

        // Recentraliza a nova linha atual, já com os tamanhos finais
        inner.style.transform = `translateY(${getTranslationForLine(lineCurr)}px)`;
        inner.offsetHeight; // força o reflow
        inner.classList.remove('no-transition');

        state.slideTransitionCleanup = null;
    };

    const timeoutId = setTimeout(commitTransition, SLIDE_MS);

    state.slideTransitionCleanup = () => {
        clearTimeout(timeoutId);
        commitTransition();
    };
}

function updateLyricsDOM(data) {
    setLyricsScriptAvailable(data.lyrics_romaji);
    fillLine(dom.prevLyricsDisplay, data.prev_lyrics, data.prev_lyrics_romaji);
    fillLine(dom.nextLyricsDisplay, data.next_lyrics, data.next_lyrics_romaji);
    if (dom.upcomingLyricsDisplay) {
        fillLine(dom.upcomingLyricsDisplay, data.upcoming_lyrics, data.upcoming_lyrics_romaji);
    }
    fillVerseLine(dom.lyricsDisplay, data);
    fitLongVerse(dom.lyricsDisplay);
}

const LINE_CLASSES = {
    'line-prev': 'carousel-line prev-line',
    'line-curr': 'carousel-line curr-line',
    'line-next': 'carousel-line next-line',
    'line-upcoming': 'carousel-line upcoming-line',
};

// Esvazia as linhas e volta o carrossel para o topo, sem animação
export function resetCarousel() {
    Object.keys(LINE_CLASSES).forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = '';
        el.className = LINE_CLASSES[id];
    });
    const inner = carouselInner();
    if (inner) {
        inner.classList.add('no-transition');
        inner.style.transform = 'translateY(0)';
        inner.offsetHeight;
        inner.classList.remove('no-transition');
    }
}
