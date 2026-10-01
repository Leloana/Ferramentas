// Controles da partida na TV: tom, velocidade, pausar, barra da música, modo de
// sincronia da letra (palavra/verso) e modo de pontuação.
import { state } from '../core/state.js';
import { dom } from '../core/dom.js';
import { iconSvg } from '../core/icons.js';
import { formatTime, paintProgressSlider } from './highlight-loop.js';
import { sendToRoom } from './session.js';

const TRANSPOSE_LIMIT = 6;
const SPEED_MIN = 0.75;
const SPEED_MAX = 1.5;
const SPEED_STEP = 0.05;

function updateAudioGraph(transpose) {
    if (state.audioManager) {
        state.audioManager.updateTranspose(transpose);
        state.jungleNode = state.audioManager.jungleNode;
    }
    // a afinação compara com a melodia no tom que está tocando
    sendToRoom({ type: 'transpose', semitones: transpose });
}

function updatePitchUI() {
    if (!dom.pitchValue) return;
    if (state.currentTranspose === 0) {
        dom.pitchValue.innerText = 'Normal';
    } else {
        dom.pitchValue.innerText = (state.currentTranspose > 0 ? '+' : '') + state.currentTranspose;
    }
}

function updateSpeedUI() {
    if (!dom.speedValue) return;
    dom.speedValue.innerText = state.currentSpeed.toFixed(2) + 'x';
}

function updateSyncModeButton() {
    if (!dom.btnSyncMode) return;
    if (state.syncMode === 'verse') {
        dom.btnSyncMode.innerHTML = `${iconSvg('sync-verse')}<span>Verso</span>`;
        dom.btnSyncMode.title = 'Sincronia por verso — Clique para alternar para palavras';
        dom.btnSyncMode.classList.add('btn-sync-mode--active');
    } else {
        dom.btnSyncMode.innerHTML = `${iconSvg('sync-word')}<span>Palavra</span>`;
        dom.btnSyncMode.title = 'Sincronia por palavra — Clique para alternar para verso';
        dom.btnSyncMode.classList.remove('btn-sync-mode--active');
    }
}

function setScoreMode(mode) {
    const btn = dom.btnScoreMode;
    if (!btn) return;
    const normalized = mode === 'words' ? 'words' : 'timing';
    btn.setAttribute('data-mode', normalized);
    if (normalized === 'words') {
        btn.innerHTML = `${iconSvg('score-words')}<span>Só palavras</span>`;
        btn.title = 'Pontuação: apenas palavras acertadas — Clique para incluir o tempo';
    } else {
        btn.innerHTML = `${iconSvg('metronome')}<span>Palavras + tempo</span>`;
        btn.title = 'Pontuação: palavras + tempo correto — Clique para pontuar só palavras';
    }
    btn.classList.toggle('btn-score-mode--active', normalized === 'words');
    localStorage.setItem('karaoke_scoring_mode', normalized);
}

export function currentScoringMode() {
    return (dom.btnScoreMode && dom.btnScoreMode.getAttribute('data-mode')) || 'timing';
}

function changeTranspose(delta) {
    const next = state.currentTranspose + delta;
    if (next < -TRANSPOSE_LIMIT || next > TRANSPOSE_LIMIT) return;
    state.currentTranspose = next;
    updatePitchUI();
    updateAudioGraph(state.currentTranspose);
}

function changeSpeed(delta) {
    if (delta < 0 ? state.currentSpeed <= SPEED_MIN : state.currentSpeed >= SPEED_MAX) return;
    state.currentSpeed = Math.round((state.currentSpeed + delta) * 100) / 100;
    updateSpeedUI();
    dom.audioPlayer.playbackRate = state.currentSpeed;
}

function setPauseButton(paused) {
    if (!dom.btnPausePlay) return;
    dom.btnPausePlay.innerText = paused ? 'RETOMAR' : 'PAUSAR';
    if (paused) dom.btnPausePlay.setAttribute('data-paused', 'true');
    else dom.btnPausePlay.removeAttribute('data-paused');
}

function togglePause() {
    if (dom.audioPlayer.paused) {
        dom.audioPlayer.play();
        setPauseButton(false);
        if (state.audioContext && state.audioContext.state === 'suspended') {
            state.audioContext.resume();
        }
    } else {
        dom.audioPlayer.pause();
        setPauseButton(true);
    }
}

function initProgressSlider(slider) {
    slider.oninput = (e) => {
        state.isUserDraggingProgress = true;
        const pct = parseFloat(e.target.value);
        paintProgressSlider(pct);
        if (dom.audioPlayer.duration) {
            const targetTime = (pct / 100) * dom.audioPlayer.duration;
            const timeCurrent = document.getElementById('song-time-current');
            if (timeCurrent) timeCurrent.innerText = formatTime(targetTime);
            const timeRemaining = document.getElementById('song-time-remaining');
            if (timeRemaining) timeRemaining.innerText = '-' + formatTime(Math.max(0, dom.audioPlayer.duration - targetTime));
        }
    };

    slider.onchange = (e) => {
        state.isUserDraggingProgress = false;
        if (dom.audioPlayer.duration) {
            const targetTime = (parseFloat(e.target.value) / 100) * dom.audioPlayer.duration;
            dom.audioPlayer.currentTime = targetTime;
            sendToRoom({ type: 'playback_time', current_time: targetTime });
        }
    };
}

export function initGameControls() {
    // Estilo de pontuação: botão toggle único (tempo+palavras vs. só palavras),
    // no mesmo padrão do botão de sincronia de letras.
    if (dom.btnScoreMode) {
        setScoreMode(localStorage.getItem('karaoke_scoring_mode') || 'timing');
        dom.btnScoreMode.onclick = () => {
            setScoreMode(dom.btnScoreMode.getAttribute('data-mode') === 'words' ? 'timing' : 'words');
        };
    }

    if (dom.btnPitchMinus) dom.btnPitchMinus.onclick = () => changeTranspose(-1);
    if (dom.btnPitchPlus) dom.btnPitchPlus.onclick = () => changeTranspose(1);
    if (dom.btnSpeedMinus) dom.btnSpeedMinus.onclick = () => changeSpeed(-SPEED_STEP);
    if (dom.btnSpeedPlus) dom.btnSpeedPlus.onclick = () => changeSpeed(SPEED_STEP);
    if (dom.btnPausePlay) dom.btnPausePlay.onclick = togglePause;
    if (dom.songProgressSlider) initProgressSlider(dom.songProgressSlider);

    // Sincronia da letra: palavra por palavra ou verso inteiro
    if (dom.btnSyncMode) {
        if (localStorage.getItem('karaoke_sync_mode') === 'verse') {
            state.syncMode = 'verse';
        }
        updateSyncModeButton();
        dom.btnSyncMode.onclick = () => {
            state.syncMode = state.syncMode === 'word' ? 'verse' : 'word';
            localStorage.setItem('karaoke_sync_mode', state.syncMode);
            updateSyncModeButton();
        };
    }
}

// Volta tom, velocidade, barra da música e o botão de pausa ao padrão
export function resetControls() {
    state.currentTranspose = 0;
    state.currentSpeed = 1.0;
    state.isUserDraggingProgress = false;
    if (dom.pitchValue) dom.pitchValue.innerText = 'Normal';
    if (dom.speedValue) dom.speedValue.innerText = '1.0x';
    if (dom.songProgressSlider) {
        dom.songProgressSlider.value = 0;
        dom.songProgressSlider.style.background = 'var(--track)';
        delete dom.songProgressSlider.dataset.pct;
    }
    const timeCurrent = document.getElementById('song-time-current');
    if (timeCurrent) timeCurrent.innerText = '0:00';
    const timeRemaining = document.getElementById('song-time-remaining');
    if (timeRemaining) timeRemaining.innerText = '-0:00';
    dom.btnStart.disabled = false;
    dom.btnStart.innerText = 'INICIAR';
    setPauseButton(false);
}
