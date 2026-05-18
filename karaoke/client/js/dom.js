const $ = (id) => document.getElementById(id);

export const dom = {
    get songListEl() { return $('song-list'); },
    get selectionArea() { return $('selection-area'); },
    get gameArea() { return $('game-area'); },
    get lyricsDisplay() { return $('line-curr'); },
    get prevLyricsDisplay() { return $('line-prev'); },
    get nextLyricsDisplay() { return $('line-next'); },
    get btnStart() { return $('btn-start'); },
    get btnExit() { return $('btn-exit'); },
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
};

export const $id = $;
