// Voz guia: a música com a voz original, para quem não sabe cantar ela.
//
// Antes era um segundo <audio> (vocal.mp3) correndo atrás do instrumental: as
// gravações mostraram a voz sempre 80–200 ms atrasada, e os saltos de correção
// não davam conta. Agora não há o que sincronizar: o servidor mistura
// instrumental + voz num arquivo só (/songs/<id>/audio?guide=50|100, gerado uma
// vez e guardado) e o player principal toca esse arquivo no lugar do
// instrumental. A voz fica exatamente no tempo da gravação, passa pelo mesmo tom
// e pela mesma velocidade, e o instrumental puro continua lá para quando desliga.
//
// O controle tem três posições: desligada (0), metade (50%) e voz normal (100%).
import { state } from '../core/state.js';
import { dom } from '../core/dom.js';
import { sendPlayerEvent } from '../game/game-events.js';

const STORAGE_KEY = 'karaoke_guide_volume';
const LEVELS = [0, 0.5, 1];
// troca o arquivo só quando o slider parar (arrastar não baixa cada posição)
const APPLY_DELAY_MS = 350;

function snap(v) {
    const x = Number.isFinite(v) ? v : 0;
    return LEVELS.reduce((best, lv) => (Math.abs(lv - x) < Math.abs(best - x) ? lv : best), 0);
}

export function savedGuideVolume() {
    try {
        return snap(parseFloat(localStorage.getItem(STORAGE_KEY)));
    } catch (e) {
        return 0;
    }
}

// Endereço do áudio da música: instrumental puro ou a mixagem com a voz.
export function songAudioUrl(songId, level = savedGuideVolume()) {
    const base = `/songs/${encodeURIComponent(songId)}/audio`;
    return level > 0 ? `${base}?guide=${Math.round(level * 100)}` : base;
}

function paintValue(vol) {
    const label = document.getElementById('guide-volume-value');
    if (label) label.textContent = vol === 0 ? 'Desligada' : vol === 1 ? 'Normal' : Math.round(vol * 100) + '%';
}

// Troca de música: lembra qual é, para trocar o arquivo quando o nível mudar.
export function setGuideSong(songId) {
    state.guideSongId = songId;
    const block = document.getElementById('guide-volume-block');
    if (block) block.hidden = false;
}

// Troca o arquivo do player sem perder a posição, a velocidade nem o play/pausa.
function swapSource(url) {
    const audio = dom.audioPlayer;
    if (!audio || !state.guideSongId) return;
    if (audio.getAttribute('src') === url) return;
    const hadMedia = !!audio.getAttribute('src') && audio.readyState > 0;
    const t = audio.currentTime;
    const rate = audio.playbackRate;
    const wasPlaying = !audio.paused && !audio.ended;
    audio.src = url;
    if (!hadMedia) return;
    audio.addEventListener('loadedmetadata', () => {
        try { audio.currentTime = t; } catch (e) { /* ainda sem metadados */ }
        audio.playbackRate = rate;  // o load volta para defaultPlaybackRate
        if (wasPlaying) audio.play().catch(() => {});
    }, { once: true });
}

export function applyGuideLevel(level = savedGuideVolume()) {
    if (state.guideSongId) swapSource(songAudioUrl(state.guideSongId, level));
}

export function initGuideVocal() {
    const slider = document.getElementById('guide-volume-slider');
    if (!slider) return;
    const vol = savedGuideVolume();
    slider.value = vol;
    paintValue(vol);
    slider.addEventListener('input', () => {
        const v = snap(parseFloat(slider.value));
        slider.value = v;
        try { localStorage.setItem(STORAGE_KEY, String(v)); } catch (e) { /* sem storage */ }
        paintValue(v);
        clearTimeout(state.guideApplyTimer);
        state.guideApplyTimer = setTimeout(() => {
            sendPlayerEvent('guide_volume', v);
            applyGuideLevel(v);
        }, APPLY_DELAY_MS);
    });
}
