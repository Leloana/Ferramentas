import { state, setAppState } from './state.js';
import { dom } from './dom.js';
import { myRole, myRoom, isSoloMobileMode } from './config.js';
import { showToast } from './toast.js';
import { updateMicStatusPanel, checkInitialMicPermission } from './mic-status.js';
import { initSyncControls } from './sync.js';
import { connectMobileMicrophoneWebSocket } from './ws-mic.js';
import { connectDisplayWebSocket } from './ws-display.js';
import { initMobileMicView } from './mobile-mic-view.js';
import { fetchSongs, initSearch } from './selection-view.js';
import { startKaraoke, resetGameState, initGameControls } from './game-view.js';
import { initModals } from './modals.js';
import { initQueueView } from './queue-view.js';
import { openModal, closeModal } from './modal.js';

function bootstrap() {
    const appEl = document.getElementById('app');
    if (appEl) {
        appEl.setAttribute('data-role', myRole);
    }

    if (myRole === 'mic') {
        setAppState('registering');

        const roomIdEl = document.getElementById('mobile-room-id');
        if (roomIdEl) roomIdEl.innerText = myRoom;

        connectMobileMicrophoneWebSocket();
        initMobileMicView();
        initQueueView();
        return;
    }

    // Display role
    if (isSoloMobileMode) {
        state.localStreamForced = true;
        state.micSourceMode = 'pc';
        updateMicStatusPanel();
    } else {
        checkInitialMicPermission();
    }

    const btnForcePc = document.getElementById('btn-force-pc-mic');
    if (btnForcePc) {
        btnForcePc.onclick = async () => {
            try {
                const testStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                testStream.getTracks().forEach(t => t.stop());

                state.localStreamForced = true;
                state.isMobileMicrophoneConnected = false;
                state.micSourceMode = 'pc';
                updateMicStatusPanel();
                showToast("Microfone do PC ativado e pronto para cantar!", "success");
            } catch (e) {
                console.error("Erro ao ativar microfone local:", e);
                state.localStreamForced = false;
                updateMicStatusPanel();

                if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
                    showToast("Microfone bloqueado! Clique no ícone de CADEADO 🔒 ou MICROFONE 🎤 na barra de endereços (lado esquerdo) e mude para 'Permitir'.", "error", 10000);
                } else if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                    showToast("O navegador bloqueia microfone em conexões HTTP sem fio. Acesse via http://localhost:8000/ no PC para liberar!", "error", 12000);
                } else {
                    showToast("Não foi possível acessar o microfone do PC: " + e.message, "error");
                }
            }
        };
    }

    initSyncControls();
    initGameControls();
    initModals();
    initSearch();
    initQueueView();
    initHomeQrcode();

    dom.btnBack.onclick = resetGameState;
    dom.btnExit.onclick = resetGameState;
    if (dom.btnExitSidebar) {
        dom.btnExitSidebar.onclick = resetGameState;
    }

    dom.btnStart.onclick = async () => {
        const seen = localStorage.getItem('karaoke_onboarding_seen');
        const doStart = async () => {
            dom.btnStart.disabled = true;
            dom.btnStart.innerText = 'PREPARANDO...';
            try {
                await startKaraoke();
            } catch (e) {
                console.error(e);
                showToast("Erro ao iniciar: " + e.message, "error");
                dom.btnStart.disabled = false;
                dom.btnStart.innerText = 'INICIAR';
            }
        };

        if (!seen) {
            const onboardingModal = document.getElementById('onboarding-modal');
            const btnCloseOnboarding = document.getElementById('btn-close-onboarding');
            if (onboardingModal && btnCloseOnboarding) {
                // Fechar de qualquer forma (botão, ESC, clique fora, voltar) marca como
                // visto e inicia o karaokê — onClose centraliza esse comportamento.
                openModal(onboardingModal, {
                    onClose: () => {
                        localStorage.setItem('karaoke_onboarding_seen', 'true');
                        doStart();
                    },
                });
                btnCloseOnboarding.onclick = () => closeModal(onboardingModal);
            } else {
                await doStart();
            }
        } else {
            await doStart();
        }
    };

    dom.audioPlayer.onended = () => {
        console.log("Backing track finalizado. Encerrando jogo...");
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(JSON.stringify({ type: "audio_ended" }));
        }
    };

    fetchSongs();
    connectDisplayWebSocket();
}

async function initHomeQrcode() {
    const qrcodePanel = document.getElementById('header-qrcode-panel');
    const qrcodeImg = document.getElementById('header-qrcode');
    if (!qrcodePanel || !qrcodeImg) return;

    // Don't show QR on mobile devices acting as display
    if (isSoloMobileMode) {
        qrcodePanel.style.display = 'none';
        return;
    }

    let targetHost = window.location.host;
    try {
        const ipRes = await fetch('/api/get-ip');
        if (ipRes.ok) {
            const ipData = await ipRes.json();
            if (ipData.ip && ipData.ip !== '127.0.0.1') {
                const port = window.location.port ? `:${window.location.port}` : '';
                targetHost = `${ipData.ip}${port}`;
            }
        }
    } catch (e) {
        console.warn('Nao foi possivel obter o IP da rede local para o QR code:', e);
    }

    const homeUrl = `${window.location.protocol}//${targetHost}/?open=add-song`;
    qrcodeImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(homeUrl)}`;
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
} else {
    bootstrap();
}
