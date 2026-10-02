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
    lyricsFrameAt: 0,         // diagnóstico: último quadro do laço da letra
    lyricsFrameGapMax: 0,     // maior intervalo entre quadros desde o último verso (ms)
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
    micLocked: false,         // mobile/mobile-mic-view.js: partida em curso sem este celular
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
    micAutoRegistering: false,   // mobile/mic-messages.js: entrando sozinho com o apelido lembrado
    micAutoRegisterFailed: false, // ...e falhou (apelido em uso): mostra o formulário
    isActiveInGame: false,
    micVuFrame: null,         // mobile/mobile-mic-view.js: laço do medidor de volume
    micHealthCleanup: null,   // mobile/mic-health.js: tira os vigias do áudio do microfone
    micHeartbeatTimer: null,  // mobile/mic-socket.js: ping a cada 10 s
    micReconnectTimer: null,
    micLastServerAt: 0,       // última mensagem do servidor (Date.now)
    micVisibilityHooked: false,
    micReplaced: false,       // 4002: outra aba assumiu o microfone, não reconecta
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
    shareCardReturnFocus: null, // share-card.js: foco a devolver ao fechar o cartão
    shareCardData: null,        // share-card.js: dados do cartão aberto (trocar de estilo remonta)
    lastGameOver: null,       // último game_over (cartão para print)
    lobbyTurns: false,        // revezar versos (lobby.js / turns.js)
    turnOrder: null,          // [[mics do time 1], ...] da partida em curso
    songRequests: [],         // fila da noite (requests.js)
    autoNextTimer: null,
    micSongs: null,           // músicas prontas para pedir no celular
    preview: null,            // trecho tocando na lista (song-preview.js)
    gpuBlock: null,           // nome da música gerando letra (bloqueia o INICIAR)
    annotateOnlyPlayer: null, // celular: anotação só do próprio cantor
    selectSongFn: null,       // selection-view.selectSong (evita import circular)
    resetGameFn: null,        // game/session.resetGameState
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
