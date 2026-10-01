import './compat.js';
import { state, setAppState } from './state.js';
import { dom } from './dom.js';
import { myRole, myRoom, isSoloMobileMode, deviceKind, isTvBrowser } from './config.js';
import { showToast } from './toast.js';
import { resolvePublicOrigin } from './public-origin.js';
import { updateMicStatusPanel, checkInitialMicPermission } from './mic-status.js';
import { initSyncControls } from './sync.js';
import { connectMobileMicrophoneWebSocket } from './ws-mic.js';
import { connectDisplayWebSocket } from './ws-display.js';
import { initMobileMicView } from './mobile-mic-view.js';
import { fetchSongs, initSearch, selectSong } from './selection-view.js';
import { initMicRequests, initNextUpButtons } from './requests.js';
import { startKaraoke, resetGameState, initGameControls } from './game-view.js';
import { initModals } from './modals.js';
import { initQueueView } from './queue-view.js';
import { openModal, closeModal } from './modal.js';
import { initAnnotation } from './annotate.js';
import { initLyricsScriptControls } from './lyrics-script.js';
import { renderIcons } from './icons.js';
import { initTabs } from './tabs.js';
import { initTvNav } from './tv-nav.js';
import { enhanceSelects } from './select.js';
import { initLobby, validateLobby } from './lobby.js';
import { initGuideVocal } from './guide-vocal.js';
import { fetchProfile, renderProfile } from './profile-view.js';
import { initPlayersModal } from './players-modal.js';
import { initStatusPanel } from './status-panel.js';
import { initCoverPicker } from './cover-picker.js';
import { initTheme } from './theme.js';
import { stopReplay } from './replay.js';

function bootstrap() {
    const appEl = document.getElementById('app');
    if (appEl) {
        appEl.setAttribute('data-role', myRole);
    }
    document.documentElement.setAttribute('data-device', deviceKind);

    renderIcons();
    initTheme();
    enhanceSelects();
    initTvNav();

    if (myRole === 'mic') {
        setAppState('registering');
        initMicTabs();
        initMicRequests();
        initAnnotation();  // cada cantor anota os próprios versos no fim
        initModals(); // "Adicionar música" padrão também no celular-microfone

        const roomIdEl = document.getElementById('mobile-room-id');
        if (roomIdEl) roomIdEl.innerText = myRoom;

        connectMobileMicrophoneWebSocket();
        initMobileMicView();
        initLyricsScriptControls();
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
                showToast("Microfone local ativado!", "success");
            } catch (e) {
                console.error("Erro ao ativar microfone local:", e);
                state.localStreamForced = false;
                updateMicStatusPanel();

                if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
                    showToast("Microfone bloqueado! Clique no ícone de cadeado ou de microfone na barra de endereços (lado esquerdo) e mude para 'Permitir'.", "error", 10000);
                } else if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                    showToast("O navegador bloqueia microfone em conexões HTTP sem fio. Acesse via http://localhost:8000/ no PC para liberar!", "error", 12000);
                } else {
                    showToast("Não foi possível acessar o microfone local: " + e.message, "error");
                }
            }
        };
    }

    if (isTvBrowser) {
        moveScoreModeToSyncBar();
        movePausePlayToProgress();
    }
    initSyncControls();
    initGuideVocal();
    initPlayersModal();
    state.selectSongFn = selectSong;
    state.resetGameFn = resetGameState;
    initNextUpButtons();
    initStatusPanel();
    initCoverPicker();
    initGameControls();
    initModals();
    initLobby();
    initAnnotation();
    initLyricsScriptControls();
    initSearch();
    initQueueView();
    initHomeQrcode();

    dom.btnBack.onclick = resetGameState;
    const headerBack = document.getElementById('btn-header-back');
    if (headerBack) headerBack.onclick = () => dom.btnBack.click();
    dom.btnExit.onclick = resetGameState;
    if (dom.btnExitSidebar) {
        dom.btnExitSidebar.onclick = resetGameState;
    }

    dom.btnStart.onclick = async () => {
        const seen = localStorage.getItem('karaoke_onboarding_seen');
        const doStart = async () => {
            if (!validateLobby()) return;
            if (state.gpuBlock) return;  // mutex de GPU (queue-view.js)
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

// TV: a forma de pontuação vai para a faixa de ajustes embaixo do lobby,
// deixando a coluna da direita só com os cantores e o INICIAR.
function moveScoreModeToSyncBar() {
    const score = document.getElementById('lobby-score');
    const inner = document.querySelector('#sync-controls .sync-controls-inner');
    if (score && inner) inner.appendChild(score);
}

// TV: pausar ao lado da barra de tempo, para a letra ganhar a altura dos botões
function movePausePlayToProgress() {
    const btn = document.getElementById('btn-pause-play');
    const progress = document.querySelector('.song-progress-container');
    if (btn && progress) progress.appendChild(btn);
}

async function initHomeQrcode() {
    const qrcodePanel = document.getElementById('header-qrcode-panel');
    const qrcodeImg = document.getElementById('header-qrcode');
    if (!qrcodePanel || !qrcodeImg) return;

    // Don't show QR on mobile devices acting as display
    if (isSoloMobileMode) {
        qrcodePanel.hidden = true;
        return;
    }

    const homeUrl = `${await resolvePublicOrigin()}/?open=add-song`;
    qrcodeImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(homeUrl)}`;
}

// Aba "Perfil" do celular: o histórico do apelido registrado neste aparelho.
async function showMyProfile() {
    const view = document.getElementById('mic-profile-view');
    if (!view) return;
    const logout = document.getElementById('btn-mic-logout');
    if (logout) logout.hidden = !state.mobileNickname;
    if (!state.mobileNickname) {
        renderProfile(view, null);
        return;
    }
    try {
        renderProfile(view, await fetchProfile(state.mobileNickname));
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// Abas do celular-microfone (Microfone | Adicionar | Perfil). O atributo vai também no
// #app porque as regras de estado em states.css partem do #app.
function initMicTabs() {
    const appEl = document.getElementById('app');
    document.querySelectorAll('.js-open-add-song').forEach((btn) => {
        btn.addEventListener('click', () => {
            const open = document.getElementById('btn-open-add-song');
            if (open) open.click();
        });
    });
    initTabs('mobile-mic-area', {
        onSelect: (tab) => {
            stopReplay();  // gravação do perfil não segue tocando em outra aba
            appEl.setAttribute('data-mic-tab', tab);
            if (tab === 'profile') showMyProfile();
        },
    });
    appEl.setAttribute('data-mic-tab', document.getElementById('mobile-mic-area').getAttribute('data-mic-tab') || 'mic');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
} else {
    bootstrap();
}
