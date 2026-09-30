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
    annotateRecordingId: null, // gravação da última partida (botão lápis da tela final)
    annotateData: null,
    lastFocusedSong: null,
    gameGeneration: 0,        // muda a cada início/saída; cancela awaits antigos
    gameReconnectTimer: null,
    timeSyncTimer: null,
    wakeLock: null,           // wake-lock.js
    wakeLockWanted: false,
    replay: null,             // replay.js (ouvir a apresentação)
    lastGameOver: null,       // último game_over (cartão para print)
    lobbyTurns: false,        // revezar versos (lobby.js / turns.js)
    turnOrder: null,          // [[mics do time 1], ...] da partida em curso
    lobbySeats: [],        // lobby: [{ mic, team }] — mesmo time = dupla/trio (lobby.js)
    lobbyMics: [],         // celulares registrados na sala
    scoreGroups: null,     // times da partida em curso [{ team, mics }] (score-bars.js)
    pickedYoutube: null,   // resultado escolhido na busca do YouTube (youtube-search.js) // último card de música focado pelo controle remoto (tv-nav.js)
};

export function setAppState(stateName) {
    const appEl = document.getElementById('app');
    const changed = state.currentAppState !== stateName;
    if (appEl) {
        appEl.setAttribute('data-state', stateName);
    }
    state.currentAppState = stateName;
    // tela nova começa do topo (não herda a rolagem da anterior)
    if (changed) window.scrollTo(0, 0);
}
