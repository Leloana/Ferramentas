import { state } from './state.js';
import { AudioLifecycleManager } from './audio-lifecycle-manager.js';
import { showToast } from './toast.js';
import { dom } from './dom.js';

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
                showToast("Por favor, digite um apelido!", "warning");
                return;
            }
            btnMobileRegister.disabled = true;
            btnMobileRegister.innerText = "REGISTRANDO...";
            if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN) {
                state.mobileWs.send(JSON.stringify({ type: "register_name", name: name }));
            } else {
                showToast("Conexão indisponível. Tente novamente em instantes.", "error");
                btnMobileRegister.disabled = false;
                btnMobileRegister.innerText = "Confirmar Apelido";
            }
        };
    }

    if (btnMobileActivate) {
        btnMobileActivate.onclick = async () => {
            btnMobileActivate.disabled = true;
            btnMobileActivate.innerText = "ATIVANDO...";

            try {
                if (state.audioManager) {
                    await state.audioManager.destroy();
                    state.audioManager = null;
                }

                state.audioManager = new AudioLifecycleManager({
                    captureMic: true,
                    onAudioChunk: (data) => {
                        if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN && !state.micMuted && state.isSingingActive) {
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

                btnMobileActivate.innerHTML = `<svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v1a7 7 0 0 1-14 0v-1"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg><span>ATIVO</span>`;
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
                btnMobileActivate.innerText = "LIGAR MIC";
            }
        };
    }

    if (btnMobileMute) {
        btnMobileMute.onclick = () => {
            state.micMuted = !state.micMuted;
            if (state.micMuted) {
                btnMobileMute.innerText = "🎙️ Desmutar Microfone";
                btnMobileMute.classList.add('btn-mobile-mute--muted');
                if (btnMobileActivate) {
                    btnMobileActivate.classList.remove('btn-mobile-activate--active');
                    btnMobileActivate.classList.add('btn-mobile-activate--muted');
                    const btnSpan = btnMobileActivate.querySelector('span');
                    if (btnSpan) btnSpan.innerText = 'MUDO';
                }
            } else {
                btnMobileMute.innerText = "🎙️ Mutar Microfone";
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
