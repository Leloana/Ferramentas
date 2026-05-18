import { state } from './state.js';
import { dom } from './dom.js';
import { myRole, myRoom, isSoloMobileMode } from './config.js';
import { showToast } from './toast.js';
import { updateMicStatusPanel, checkInitialMicPermission } from './mic-status.js';
import { initSyncControls } from './sync.js';
import { connectMobileMicrophoneWebSocket } from './ws-mic.js';
import { connectDisplayWebSocket } from './ws-display.js';
import { initMobileMicView } from './mobile-mic-view.js';
import { fetchSongs, initSearch } from './selection-view.js';
import { startKaraoke, resetGameState } from './game-view.js';
import { initModals } from './modals.js';

function bootstrap() {
    if (myRole === 'mic') {
        const containerEl = document.querySelector('.container');
        const headerEl = document.querySelector('.app-header');
        if (containerEl) containerEl.style.display = 'none';
        if (headerEl) headerEl.style.display = 'none';

        const mobileMicArea = document.getElementById('mobile-mic-area');
        if (mobileMicArea) mobileMicArea.style.display = 'flex';

        const roomIdEl = document.getElementById('mobile-room-id');
        if (roomIdEl) roomIdEl.innerText = myRoom;

        connectMobileMicrophoneWebSocket();
        initMobileMicView();
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
    initModals();
    initSearch();

    dom.btnBack.onclick = resetGameState;
    dom.btnExit.onclick = resetGameState;

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
                dom.btnStart.innerText = 'INICIAR CANTO';
            }
        };

        if (!seen) {
            const onboardingModal = document.getElementById('onboarding-modal');
            const btnCloseOnboarding = document.getElementById('btn-close-onboarding');
            if (onboardingModal && btnCloseOnboarding) {
                onboardingModal.style.display = 'flex';
                btnCloseOnboarding.onclick = async () => {
                    onboardingModal.style.display = 'none';
                    localStorage.setItem('karaoke_onboarding_seen', 'true');
                    await doStart();
                };
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

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
} else {
    bootstrap();
}
