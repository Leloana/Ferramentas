import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { AudioLifecycleManager } from '../audio/audio-lifecycle-manager.js';
import { showToast } from '../core/toast.js';
import { dom } from '../core/dom.js';
import { keepScreenOn } from '../core/wake-lock.js';
import { deviceInfo } from '../game/game-events.js';
import { micDeviceId, saveMicName } from '../core/config.js';
import { watchMicHealth, stopMicHealth, micRunning, MAX_BUFFERED_BYTES } from './mic-health.js';
import { initReactionsBar } from './reactions-bar.js';

const ATTENTION_CLASS = 'btn-mobile-activate--attention';

function activateButton() {
    return document.getElementById('btn-mobile-activate');
}

// Volta o botão para LIGAR MIC (o microfone só religa com um toque)
function showMicOff() {
    const btn = activateButton();
    if (!btn) return;
    btn.disabled = false;
    btn.classList.remove('btn-mobile-activate--active', 'btn-mobile-activate--muted');
    btn.innerHTML = `${iconSvg('mic')}<span>LIGAR MIC</span>`;
    const box = document.getElementById('mobile-active-mic-container');
    if (box) box.removeAttribute('data-mic-active');
    // mudo não sobrevive à religada: senão o botão diz ATIVO e o áudio é descartado
    state.micMuted = false;
    const mute = document.getElementById('btn-mobile-mute');
    if (mute) {
        mute.innerHTML = `${iconSvg('mic-off')} Mutar microfone`;
        mute.classList.remove('btn-mobile-mute--muted');
    }
    stopVu();
}

function stopVu() {
    if (state.micVuFrame) {
        cancelAnimationFrame(state.micVuFrame);
        state.micVuFrame = null;
    }
}

function onMicLost() {
    showMicOff();
    // a faixa acabou: pede o toque mesmo que o navegador ainda não a dê por encerrada
    const btn = activateButton();
    if (btn && state.isActiveInGame) btn.classList.add(ATTENTION_CLASS);
    showToast('O microfone desligou. Toque em LIGAR MIC.', 'error');
}

// No jogo e sem microfone (página recarregou, faixa acabou): botão pulsando.
export function remindMicIfOff() {
    const btn = activateButton();
    // espectador na rodada seguinte: o aviso sai
    if (btn) btn.classList.toggle(ATTENTION_CLASS, state.isActiveInGame && !micRunning());
}

export function initMobileMicView() {
    const btnMobileActivate = document.getElementById('btn-mobile-activate');
    const mobileActiveControls = document.getElementById('mobile-active-controls');
    const mobileLyricsContainer = document.getElementById('mobile-lyrics-container');
    const btnMobileMute = document.getElementById('btn-mobile-mute');
    const mobileMicVu = document.getElementById('mobile-mic-vu');

    const btnMobileRegister = dom.btnMobileRegister;
    const mobileNicknameInput = dom.mobileNicknameInput;

    if (btnMobileRegister) {
        btnMobileRegister.onclick = () => {
            const name = mobileNicknameInput.value.trim();
            if (!name) {
                showToast("Por favor, digite um apelido!", "error");
                return;
            }
            btnMobileRegister.disabled = true;
            btnMobileRegister.innerText = "REGISTRANDO...";
            if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN) {
                state.micAutoRegisterFailed = false;
                state.mobileWs.send(JSON.stringify({ type: "register_name", name: name, device: micDeviceId() }));
            } else {
                showToast("Conexão indisponível. Tente novamente em instantes.", "error");
                btnMobileRegister.disabled = false;
                btnMobileRegister.innerText = "Entrar";
            }
        };
    }

    if (btnMobileActivate) {
        btnMobileActivate.onclick = async () => {
            btnMobileActivate.disabled = true;
            btnMobileActivate.innerText = "ATIVANDO...";
            // pedido dentro do toque do usuário (exigência do Safari)
            keepScreenOn();

            try {
                stopMicHealth();
                if (state.audioManager) {
                    await state.audioManager.destroy();
                    state.audioManager = null;
                }

                state.audioManager = new AudioLifecycleManager({
                    captureMic: true,
                    onAudioChunk: (data) => {
                        // Manda a música inteira, não só os versos: o servidor recorta a
                        // janela de cada verso e a gravação da partida fica completa.
                        const ws = state.mobileWs;
                        if (!ws || ws.readyState !== WebSocket.OPEN || state.micMuted || !state.isActiveInGame) return;
                        // rede lenta: descarta em vez de empilhar (a fila atrasa o pong e derruba o socket)
                        if (ws.bufferedAmount > MAX_BUFFERED_BYTES) return;
                        ws.send(data);
                    }
                });

                await state.audioManager.init();
                await state.audioManager.start();
                watchMicHealth(state.audioManager, onMicLost);
                btnMobileActivate.classList.remove(ATTENTION_CLASS);

                if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN) {
                    state.mobileWs.send(JSON.stringify({
                        type: "client_info",
                        sample_rate: state.audioManager.audioContext.sampleRate,
                        ...deviceInfo(state.audioManager.localStream),
                    }));
                }

                const analyser = state.audioManager.getAnalyser();
                const bufferLength = analyser.frequencyBinCount;
                const dataArray = new Uint8Array(bufferLength);

                btnMobileActivate.innerHTML = `${iconSvg('mic')}<span>ATIVO</span>`;
                btnMobileActivate.classList.add('btn-mobile-activate--active');

                const mobileActiveMicContainer = document.getElementById('mobile-active-mic-container');
                if (mobileActiveMicContainer) {
                    mobileActiveMicContainer.setAttribute('data-mic-active', 'true');
                }

                function drawVU() {
                    if (!analyser || state.micMuted) {
                        if (mobileMicVu) {
                            mobileMicVu.style.transform = 'scale(1.0)';
                            mobileMicVu.style.opacity = '0';
                        }
                        state.micVuFrame = requestAnimationFrame(drawVU);
                        return;
                    }
                    analyser.getByteFrequencyData(dataArray);
                    let sum = 0;
                    for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
                    const average = sum / bufferLength;

                    const scale = 1.0 + (average / 128.0) * 0.45;
                    const opacity = Math.min(average / 48.0, 1.0);

                    if (mobileMicVu) {
                        mobileMicVu.style.transform = `scale(${scale})`;
                        mobileMicVu.style.opacity = opacity;
                    }

                    state.micVuFrame = requestAnimationFrame(drawVU);
                }
                // um laço só: religar o microfone não deixa o anterior rodando
                stopVu();
                drawVU();

                showToast("Microfone capturando áudio!", "success");
            } catch (e) {
                console.error(e);
                showToast("Erro ao ativar microfone: " + e.message, "error");
                btnMobileActivate.disabled = false;
                btnMobileActivate.innerHTML = `${iconSvg('mic')}<span>LIGAR MIC</span>`;
            }
        };
    }

    if (btnMobileMute) {
        btnMobileMute.onclick = () => {
            state.micMuted = !state.micMuted;
            if (state.micMuted) {
                btnMobileMute.innerHTML = `${iconSvg('mic')} Desmutar microfone`;
                btnMobileMute.classList.add('btn-mobile-mute--muted');
                if (btnMobileActivate) {
                    btnMobileActivate.classList.remove('btn-mobile-activate--active');
                    btnMobileActivate.classList.add('btn-mobile-activate--muted');
                    const btnSpan = btnMobileActivate.querySelector('span');
                    if (btnSpan) btnSpan.innerText = 'MUDO';
                }
            } else {
                btnMobileMute.innerHTML = `${iconSvg('mic-off')} Mutar microfone`;
                btnMobileMute.classList.remove('btn-mobile-mute--muted');
                if (btnMobileActivate) {
                    btnMobileActivate.classList.remove('btn-mobile-activate--muted');
                    btnMobileActivate.classList.add('btn-mobile-activate--active');
                    const btnSpan = btnMobileActivate.querySelector('span');
                    if (btnSpan) btnSpan.innerText = 'ATIVO';
                }
            }
        };
    }

    // Perfil: sair do apelido e voltar à tela de nome, na mesma sala (trocar de cantor)
    const btnLogout = document.getElementById('btn-mic-logout');
    if (btnLogout) {
        btnLogout.onclick = async () => {
            saveMicName('');  // não entra sozinho de novo com o apelido antigo
            stopMicHealth();
            if (state.audioManager) {
                await state.audioManager.destroy();
                state.audioManager = null;
            }
            window.location.reload();
        };
    }

    const btnMobileExitMic = document.getElementById('btn-mobile-exit-mic');
    if (btnMobileExitMic) {
        btnMobileExitMic.onclick = async () => {
            saveMicName('');  // saiu de propósito: não entra sozinho de novo
            stopMicHealth();
            if (state.audioManager) {
                await state.audioManager.destroy();
                state.audioManager = null;
            }
            window.location.href = window.location.origin + window.location.pathname;
        };
    }
    initReactionsBar();
}
