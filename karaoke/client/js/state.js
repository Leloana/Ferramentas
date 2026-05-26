export const state = {
    selectedSongId: null,
    allSongs: [],
    ws: null,
    mobileWs: null,
    transcriptionActiveTimer: null,
    audioContext: null,
    currentSegments: null,
    currentSegmentData: null,
    lastSegmentLyricsTimed: null,
    animationId: null,
    syncOffset: 0,
    isFirstSegment: true,
    totalPauseDuration: 0,
    pauseStartTarget: 0,
    isMobileMicrophoneConnected: false,
    localStreamForced: false,
    micSourceMode: 'pc',
    isSingingActive: false,
    isOutroActive: false,
    outroStartPlayerTime: 0,
    outroTotalDuration: 0,
    micMuted: false,
    activeUploadTab: 'youtube',
    currentTranspose: 0,
    currentSpeed: 1.0,
    isUserDraggingProgress: false,
    mediaElementSource: null,
    jungleNode: null,
    localStream: null,
    micSourceNode: null,
    micProcessorNode: null,
    mobileNickname: null,
    isActiveInGame: false,
    activePlayers: null,
    gameMode: null,
    currentAppState: 'idle',
    audioManager: null,
    syncMode: 'word', // 'word' | 'verse'
};

export function setAppState(stateName) {
    const appEl = document.getElementById('app');
    if (appEl) {
        appEl.setAttribute('data-state', stateName);
    }
    state.currentAppState = stateName;
}
