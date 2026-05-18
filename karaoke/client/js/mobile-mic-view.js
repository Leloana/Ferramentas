import { state } from './state.js';
import { getMicrophoneStream } from './mic-stream.js';
import { showToast } from './toast.js';

export function initMobileMicView() {
    const btnMobileActivate = document.getElementById('btn-mobile-activate');
    const mobileActiveControls = document.getElementById('mobile-active-controls');
    const mobileLyricsContainer = document.getElementById('mobile-lyrics-container');
    const btnMobileMute = document.getElementById('btn-mobile-mute');
    const mobileMicVu = document.getElementById('mobile-mic-vu');

    if (btnMobileActivate) {
        btnMobileActivate.onclick = async () => {
            btnMobileActivate.disabled = true;
            btnMobileActivate.innerText = "ATIVANDO...";

            try {
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const stream = await getMicrophoneStream();

                if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN) {
                    state.mobileWs.send(JSON.stringify({ type: "client_info", sample_rate: audioCtx.sampleRate }));
                }

                await audioCtx.audioWorklet.addModule('/js/worklets/audio-processor.js');
                const source = audioCtx.createMediaStreamSource(stream);
                const processor = new AudioWorkletNode(audioCtx, 'audio-processor');

                const analyser = audioCtx.createAnalyser();
                analyser.fftSize = 256;
                const bufferLength = analyser.frequencyBinCount;
                const dataArray = new Uint8Array(bufferLength);
                source.connect(analyser);

                processor.port.onmessage = (event) => {
                    if (state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN && !state.micMuted && state.isSingingActive) {
                        state.mobileWs.send(event.data);
                    }
                };

                source.connect(processor);
                processor.connect(audioCtx.destination);

                btnMobileActivate.innerHTML = `<svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v1a7 7 0 0 1-14 0v-1"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg><span>ATIVO</span>`;
                btnMobileActivate.classList.add('btn-mobile-activate--active');

                if (mobileActiveControls) mobileActiveControls.style.display = 'flex';
                if (mobileLyricsContainer) mobileLyricsContainer.style.display = 'flex';
                if (mobileMicVu) mobileMicVu.style.display = 'block';

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
        btnMobileExitMic.onclick = () => {
            window.location.href = window.location.origin + window.location.pathname;
        };
    }
}
