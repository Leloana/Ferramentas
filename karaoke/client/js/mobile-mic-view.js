import { state } from './state.js';
import { iconSvg } from './icons.js';
import { AudioLifecycleManager } from './audio-lifecycle-manager.js';
import { showToast } from './toast.js';
import { dom } from './dom.js';
import { keepScreenOn } from './wake-lock.js';

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
                state.mobileWs.send(JSON.stringify({ type: "register_name", name: name }));
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
                if (state.audioManager) {
                    await state.audioManager.destroy();
                    state.audioManager = null;
                }

                state.audioManager = new AudioLifecycleManager({
                    captureMic: true,
                    onAudioChunk: (data) => {
                        // Manda a música inteira, não só os versos: o servidor recorta a
                        // janela de cada verso e a gravação da partida fica completa.
                        if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN && !state.micMuted && state.isActiveInGame) {
                            state.mobileWs.send(data);
                        }
                    }
                });

                await state.audioManager.init();
                await state.audioManager.start();

                if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN) {
                    state.mobileWs.send(JSON.stringify({ type: "client_info", sample_rate: state.audioManager.audioContext.sampleRate }));
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
                        requestAnimationFrame(drawVU);
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

                    requestAnimationFrame(drawVU);
                }
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

    const btnMobileExitMic = document.getElementById('btn-mobile-exit-mic');
    if (btnMobileExitMic) {
        btnMobileExitMic.onclick = async () => {
            if (state.audioManager) {
                await state.audioManager.destroy();
                state.audioManager = null;
            }
            window.location.href = window.location.origin + window.location.pathname;
        };
    }
}
