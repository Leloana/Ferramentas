const $ = (id) => document.getElementById(id);

export const dom = {
    get songListEl() { return $('song-list'); },
    get selectionArea() { return $('selection-area'); },
    get gameArea() { return $('game-area'); },
    get lyricsDisplay() { return $('line-curr'); },
    get prevLyricsDisplay() { return $('line-prev'); },
    get nextLyricsDisplay() { return $('line-next'); },
    get upcomingLyricsDisplay() { return $('line-upcoming'); },
    get btnStart() { return $('btn-start'); },
    get btnExit() { return $('btn-exit'); },
    get btnExitSidebar() { return $('btn-exit-sidebar'); },
    get btnBack() { return $('btn-back'); },
    get audioPlayer() { return $('audio-player'); },
    get syncValueEl() { return $('sync-value'); },
    get btnSyncMinus() { return $('btn-sync-minus'); },
    get btnSyncPlus() { return $('btn-sync-plus'); },
    get backingVolumeSlider() { return $('backing-volume-slider'); },
    get backingVolumeValue() { return $('backing-volume-value'); },
    get toastContainer() { return $('toast-container'); },
    get addSongModal() { return $('add-song-modal'); },
    get lrcEditorModal() { return $('lrc-editor-modal'); },
    get loadingOverlay() { return $('loading-overlay'); },
    get loadingStatusTitle() { return $('loading-status-title'); },
    get loadingStatusDesc() { return $('loading-status-desc'); },
    get addSongForm() { return $('add-song-form'); },
    get lrcEditorForm() { return $('lrc-editor-form'); },
    get pairingModal() { return $('pairing-modal'); },
    get searchInput() { return $('search-input'); },
    get songProgressSlider() { return $('song-progress-slider'); },
    get btnPitchMinus() { return $('btn-pitch-minus'); },
    get btnPitchPlus() { return $('btn-pitch-plus'); },
    get pitchValue() { return $('pitch-value'); },
    get btnSpeedMinus() { return $('btn-speed-minus'); },
    get btnSpeedPlus() { return $('btn-speed-plus'); },
    get speedValue() { return $('speed-value'); },
    get btnPausePlay() { return $('btn-pause-play'); },
    // Multiplayer TV Getters
    get mpSetupContainer() { return $('multiplayer-setup-container'); },
    get mpGameMode() { return $('mp-game-mode'); },
    get mpConnectedCount() { return $('mp-connected-count'); },
    get mpQueueCount() { return $('mp-queue-count'); },
    get slotP1() { return $('slot-p1'); },
    get slotP2() { return $('slot-p2'); },
    get slotP3() { return $('slot-p3'); },
    get slotP4() { return $('slot-p4'); },
    get slotBoxP2() { return $('slot-box-p2'); },
    get slotBoxP3() { return $('slot-box-p3'); },
    get slotBoxP4() { return $('slot-box-p4'); },
    // Multiplayer Mobile Getters
    get mobileRegisterContainer() { return $('mobile-register-container'); },
    get mobileNicknameInput() { return $('mobile-nickname-input'); },
    get btnMobileRegister() { return $('btn-mobile-register'); },
    get mobileRegisterError() { return $('mobile-register-error'); },
    get mobileQueueContainer() { return $('mobile-queue-container'); },
    get mobileQueuePosition() { return $('mobile-queue-position'); },
    get mobileActiveMicContainer() { return $('mobile-active-mic-container'); },
    // Queue Getters
    get queueFab() { return $('queue-fab'); },
    get queueFabBadge() { return $('queue-fab-badge'); },
    get queueSheet() { return $('queue-sheet'); },
    get queueSheetOverlay() { return $('queue-sheet-overlay'); },
    get queueSheetClose() { return $('queue-sheet-close'); },
    get queueAddForm() { return $('queue-add-form'); },
    get queueYtUrl() { return $('queue-yt-url'); },
    get queueLanguage() { return $('queue-language'); },
    get queueLyrics() { return $('queue-lyrics'); },
    get queueAddedBy() { return $('queue-added-by'); },
    get queueSubmitBtn() { return $('queue-submit-btn'); },
    get queueItemsList() { return $('queue-items-list'); },
    get queueDisplayList() { return $('queue-display-list'); },
};

export const $id = $;

let loadingInterval = null;
const funnyPhrases = [
    "Ensinando o Whisper a cantar no tom... 🎙️🤖",
    "Pedindo educadamente para a RTX 4070 ir mais rápido... ⚡",
    "Separando a voz dos instrumentos com uma pinça digital... 🎻",
    "Afiando a agulha virtual do toca-discos... 🎶",
    "Removendo a tosse do baterista... 🥁",
    "Subornando os robôs para não desafinarem o playback... 🤖🍬",
    "Limpando os cabos virtuais para evitar chiado... 🔌",
    "Whisper está escutando a música em 10x de velocidade... ⏩",
    "Alinhando as sílabas com precisão cirúrgica... ✂️",
    "Polindo a faixa de áudio para brilhar na sua caixa de som... ✨",
    "Esfoliando as ondas sonoras... 🛁",
    "Desembaraçando as frequências graves... 🎸",
    "Passando pano nos microfones digitais... 🧼"
];

export function startLoadingOverlay(title, initialDesc, autoProgress = false) {
    if (loadingInterval) {
        clearInterval(loadingInterval);
        loadingInterval = null;
    }
    
    dom.loadingStatusTitle.innerText = title;
    
    if (autoProgress) {
        dom.loadingStatusDesc.innerHTML = `
            <div style="font-weight: 700; color: var(--accent); margin-bottom: 0.5rem;" id="loading-action-status">${initialDesc}</div>
            <div style="font-style: italic; color: var(--dim); min-height: 24px; font-size: 0.9rem;" id="loading-funny-phrase">
                ${funnyPhrases[Math.floor(Math.random() * funnyPhrases.length)]}
            </div>
            <div style="margin-top: 1rem; font-size: 0.75rem; color: #10b981; font-weight: 600; line-height: 1.4; opacity: 0.95;">
                ℹ️ Nota: O vocal e a letra são processados em primeiro plano. O Backing Track instrumental está sendo gerado via separação por Inteligência Artificial (Demucs) em segundo plano usando a sua placa NVIDIA RTX!
            </div>
        `;
        
        let timeElapsed = 0;
        loadingInterval = setInterval(() => {
            timeElapsed += 3;
            
            const funnyEl = document.getElementById('loading-funny-phrase');
            if (funnyEl) {
                funnyEl.innerText = funnyPhrases[Math.floor(Math.random() * funnyPhrases.length)];
            }
            
            const actionEl = document.getElementById('loading-action-status');
            if (actionEl) {
                if (timeElapsed < 8) {
                    actionEl.innerText = "Fase 1/3: Baixando e preparando faixa vocal principal... 🎧";
                } else if (timeElapsed < 22) {
                    actionEl.innerText = "Fase 2/3: Transcrevendo a voz com Whisper AI na GPU RTX... 🎙️🤖";
                } else {
                    actionEl.innerText = "Fase 3/3: Mapeando fonemas e alinhando sílabas para o Karaokê... 📝⚡";
                }
            }
        }, 3000);
    } else {
        dom.loadingStatusDesc.innerText = initialDesc;
    }
    
    dom.loadingOverlay.setAttribute('data-open', 'true');
}

export function stopLoadingOverlay() {
    if (loadingInterval) {
        clearInterval(loadingInterval);
        loadingInterval = null;
    }
    dom.loadingOverlay.removeAttribute('data-open');
}
