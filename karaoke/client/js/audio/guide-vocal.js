// Voz guia: o vocal separado (vocal.mp3) tocando baixinho junto do
// instrumental, para quem não sabe a música. Começa em 0% (desligada).
//
// O áudio passa pelo mesmo caminho de tom do instrumental
// (audio-lifecycle-manager.js). Aqui fica o controle de volume e a
// sincronia com o player principal (play/pausa/seek/velocidade + correção
// de deriva).
import { state } from '../core/state.js';
import { dom } from '../core/dom.js';
import { sendPlayerEvent } from '../game/game-events.js';

const STORAGE_KEY = 'karaoke_guide_volume';
// Deriva da voz guia: acima disso salta para a posição do instrumental. A velocidade
// fica sempre igual à dele: alcançar mudando a velocidade deixou a voz audivelmente
// adiantada na TV (Firefox Android). 80 ms com salto a cada conferência engasgava:
// agora 150 ms e no máximo um salto a cada RESYNC_GAP_MS.
const MAX_DRIFT_SEC = 0.15;
const RESYNC_GAP_MS = 5000;
// amostra da deriva na gravação da partida, para calibrar (event guide_drift, em ms)
const DRIFT_SAMPLE_MS = 10000;

export function savedGuideVolume() {
    try {
        const v = parseFloat(localStorage.getItem(STORAGE_KEY));
        return isNaN(v) ? 0 : v;
    } catch (e) {
        return 0;
    }
}

function paintValue(vol) {
    const label = document.getElementById('guide-volume-value');
    if (label) label.textContent = Math.round(vol * 100) + '%';
}

// Troca de música: aponta a voz guia para a música nova (sem baixar enquanto 0%).
export function setGuideSong(songId) {
    const guide = dom.guidePlayer;
    const block = document.getElementById('guide-volume-block');
    if (!guide) return;
    if (block) block.hidden = false;
    guide.preload = savedGuideVolume() > 0 ? 'auto' : 'none';
    guide.onerror = () => { if (block) block.hidden = true; };  // música sem voz separada
    guide.src = `/songs/${encodeURIComponent(songId)}/vocal`;
}

function follow(audio) {
    // o <audio> da voz guia é trocado por um clone a cada partida: sempre o atual
    const guide = () => dom.guidePlayer;
    const active = () => savedGuideVolume() > 0 && !!guide();
    let lastResync = 0;
    let lastSample = 0;
    // play/seek do instrumental: salta sempre que estiver fora
    const align = () => {
        const g = guide();
        if (g && Math.abs(g.currentTime - audio.currentTime) > MAX_DRIFT_SEC) {
            try { g.currentTime = audio.currentTime; } catch (e) { /* ainda sem metadados */ }
            lastResync = Date.now();
        }
    };
    // durante a música: salta só com folga desde o último salto
    const keepUp = () => {
        const g = guide();
        if (!g) return;
        const drift = g.currentTime - audio.currentTime;
        const now = Date.now();
        if (now - lastSample > DRIFT_SAMPLE_MS) {
            lastSample = now;
            sendPlayerEvent('guide_drift', Math.round(drift * 1000));
        }
        if (Math.abs(drift) > MAX_DRIFT_SEC && now - lastResync > RESYNC_GAP_MS) {
            sendPlayerEvent('guide_resync', Math.round(drift * 1000));
            align();
        }
    };
    const play = () => {
        const g = guide();
        g.playbackRate = audio.playbackRate;
        g.play().catch(() => {});
    };
    audio.addEventListener('play', () => {
        if (!active()) return;
        align();
        play();
    });
    audio.addEventListener('pause', () => { if (guide()) guide().pause(); });
    audio.addEventListener('ended', () => { if (guide()) guide().pause(); });
    audio.addEventListener('seeked', align);
    audio.addEventListener('ratechange', () => { if (guide()) guide().playbackRate = audio.playbackRate; });
    audio.addEventListener('timeupdate', () => {
        if (!active() || audio.paused) return;
        if (guide().paused) { align(); play(); return; }
        keepUp();
    });
}

// Chamado a cada partida: o audio-lifecycle-manager troca os elementos <audio>
// por clones ao destruir o grafo, então os ouvintes são ligados de novo.
export function attachGuideSync() {
    const audio = dom.audioPlayer;
    if (!audio || audio._guideSynced) return;
    audio._guideSynced = true;
    follow(audio);
}

export function initGuideVocal() {
    const slider = document.getElementById('guide-volume-slider');
    if (!slider) return;
    const vol = savedGuideVolume();
    slider.value = vol;
    paintValue(vol);
    slider.addEventListener('input', () => {
        const v = parseFloat(slider.value) || 0;
        try { localStorage.setItem(STORAGE_KEY, String(v)); } catch (e) { /* sem storage */ }
        paintValue(v);
        if (state.audioManager) state.audioManager.setGuideVolume(v);
        sendPlayerEvent('guide_volume', v);
        const guide = dom.guidePlayer;
        const audio = dom.audioPlayer;
        if (!guide || !audio) return;
        if (v > 0 && !audio.paused) {
            guide.preload = 'auto';
            guide.currentTime = audio.currentTime;
            guide.play().catch(() => {});
        } else if (v === 0) {
            guide.pause();
        }
    });
}
