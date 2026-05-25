import { state, setAppState } from './state.js';
import { myRoom } from './config.js';
import { showToast } from './toast.js';
import { dom } from './dom.js';

export function connectMobileMicrophoneWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${myRoom}?role=mic`;

    state.mobileWs = new WebSocket(wsUrl);
    state.mobileWs.binaryType = 'arraybuffer';

    state.mobileWs.onopen = () => {
        document.getElementById('mobile-song-title').innerText = "Aguardando registro...";
        document.getElementById('mobile-status-text').innerHTML = `🎙️ Conectado à Sala <span style="color: #a855f7; font-weight: 800;">${myRoom}</span>`;
    };

    const MIC_HANDLERS = {
        register_request(data, context) {
            const { dom } = context;
            setAppState('registering');
            if (dom.btnMobileRegister) {
                dom.btnMobileRegister.disabled = false;
                dom.btnMobileRegister.innerText = "Confirmar Apelido";
            }
            if (dom.mobileRegisterError) dom.mobileRegisterError.removeAttribute('data-visible');
        },
        register_wait(data, context) {
            const { dom } = context;
            setAppState('waiting');
            if (dom.mobileQueuePosition) {
                dom.mobileQueuePosition.innerText = data.position;
            }
        },
        registration_success(data, context) {
            const { state, dom, myRoom } = context;
            state.mobileNickname = data.name;
            showToast(`Registrado com sucesso como "${data.name}"!`, "success");
            
            const statusText = document.getElementById('mobile-status-text');
            if (statusText) {
                statusText.innerHTML = `👤 Apelido: <span style="color: var(--accent); font-weight: 800;">${data.name}</span> (Sala ${myRoom})`;
            }
            
            setAppState('singing');
        },
        registration_error(data, context) {
            const { dom } = context;
            if (dom.btnMobileRegister) {
                dom.btnMobileRegister.disabled = false;
                dom.btnMobileRegister.innerText = "Confirmar Apelido";
            }
            if (dom.mobileRegisterError) {
                dom.mobileRegisterError.innerText = data.message;
                dom.mobileRegisterError.setAttribute('data-visible', 'true');
            }
            showToast(data.message, "error");
        },
        game_started(data, context) {
            const { state } = context;
            const activePlayers = data.active_players || [];
            state.isActiveInGame = activePlayers.includes(state.mobileNickname);
            
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                if (state.isActiveInGame) {
                    lyrText.innerHTML = `<span style="color: var(--success); font-weight: 800;">Você está no jogo! 🎤</span><br>Aguardando letras...`;
                } else {
                    lyrText.innerHTML = `<span style="color: var(--dim); font-weight: 700;">Você está assistindo 👀</span><br>Aguardando próxima rodada...`;
                }
            }
        },
        pairing_status(data, context) {
            const { state, myRoom } = context;
            const statusText = document.getElementById('mobile-status-text');
            if (statusText) {
                if (data.status === 'paired') {
                    if (state.mobileNickname) {
                        statusText.innerHTML = `👤 Apelido: <span style="color: var(--accent); font-weight: 800;">${state.mobileNickname}</span> (Sala ${myRoom})`;
                    }
                } else if (data.status === 'unpaired') {
                    statusText.innerHTML = `<span style="color: var(--error); font-weight: 800;">⚠️ TV Desconectada (Sala ${myRoom})</span>`;
                }
            }
        },
        singing_state(data, context) {
            const { state } = context;
            if (state.isActiveInGame) {
                state.isSingingActive = data.active;
            } else {
                state.isSingingActive = false;
            }
        },
        segment_start(data, context) {
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) lyrText.innerText = data.lyrics;

            const songTitle = document.getElementById('mobile-song-title');
            if (songTitle && data.song_title) {
                songTitle.innerText = data.song_title;
            }
        },
        segment_result(data, context) {
            const { state } = context;
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                let myScore = data.score;
                let myTotalScore = data.total_score;
                
                if (data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname]) {
                    const pData = data.player_scores[state.mobileNickname];
                    myScore = pData.score;
                    myTotalScore = pData.total_score;
                }
                
                if (state.isActiveInGame) {
                    lyrText.innerHTML = `Segmento Anterior: <span style="color: #fde047; font-weight: 900;">${myScore}%</span><br><span style="font-size: 0.95rem; color: var(--dim); font-weight: 500;">Sua Precisão Geral: ${myTotalScore}%</span>`;
                } else {
                    lyrText.innerHTML = `<span style="color: var(--dim); font-weight: 700;">Você está assistindo 👀</span><br>Resultado da sala: ${myTotalScore}%`;
                }
            }
        },
        outro_start(data, context) {
            const { state } = context;
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                if (state.isActiveInGame) {
                    lyrText.innerHTML = `🎸 FINALIZANDO APRESENTAÇÃO<br><span style="font-size: 1rem; color: #a855f7; font-weight: 800;">Você deu o seu show! ⚡</span><br><span style="font-size: 0.9rem; color: var(--dim);">Aguardando pontuação final...</span>`;
                } else {
                    lyrText.innerHTML = `🎸 Fim da música!<br><span style="font-size: 0.9rem; color: var(--dim);">Aguardando placar final...</span>`;
                }
            }
        },
        game_over(data, context) {
            const { state } = context;
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                let myTotalScore = data.total_score;
                if (data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname] !== undefined) {
                    myTotalScore = data.player_scores[state.mobileNickname];
                }
                
                let html = `<div style="display: flex; flex-direction: column; gap: 0.75rem; width: 100%; align-items: center;">`;
                html += `<span style="font-size: 1.25rem; font-weight: 900; color: #fff; text-shadow: 0 0 10px rgba(255,255,255,0.2);">🎉 JOGO CONCLUÍDO!</span>`;
                
                if (state.isActiveInGame) {
                    html += `<span style="font-size: 0.95rem; color: var(--dim); font-weight: 700;">Sua Média: <span style="color: var(--highlight); font-weight: 900;">${myTotalScore.toFixed(1)}%</span></span>`;
                }
                
                if (data.player_scores && Object.keys(data.player_scores).length > 0) {
                    html += `<div style="width: 100%; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 0.75rem; margin-top: 0.25rem; display: flex; flex-direction: column; gap: 0.5rem; text-align: left; max-height: 150px; overflow-y: auto; box-sizing: border-box; padding-right: 4px;">`;
                    const sortedPlayers = Object.entries(data.player_scores).sort((a, b) => b[1] - a[1]);
                    sortedPlayers.forEach(([name, score], idx) => {
                        let medal = "🎤";
                        if (idx === 0) medal = "🥇";
                        else if (idx === 1) medal = "🥈";
                        else if (idx === 2) medal = "🥉";
                        const displayName = name === "PC_Local" ? "💻 PC Local" : name;
                        const isMe = name === state.mobileNickname;
                        const weight = isMe ? "800" : "600";
                        const bg = isMe ? "background: rgba(255,255,255,0.06); padding: 0.25rem 0.5rem; border-radius: 8px;" : "";
                        html += `<div style="display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: ${weight}; color: #f8fafc; ${bg}">`;
                        html += `<span>${medal} ${displayName}</span>`;
                        html += `<span style="color: var(--highlight); font-weight: 800;">${score.toFixed(1)}%</span>`;
                        html += `</div>`;
                    });
                    html += `</div>`;
                } else if (!state.isActiveInGame) {
                    html += `<span style="font-size: 0.9rem; color: var(--dim); font-weight: 700;">Placar final exibido na TV.</span>`;
                }
                html += `</div>`;
                lyrText.innerHTML = html;
            }
        }
    };

    state.mobileWs.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            console.error("Payload do microfone malformado:", e);
            return;
        }

        const handler = MIC_HANDLERS[data.type];
        if (handler) {
            const context = { state, dom, myRoom };
            handler(data, context);
        } else {
            console.warn(`Tipo de mensagem de microfone desconhecido recebido: ${data.type}`);
        }
    };

    state.mobileWs.onclose = () => {
        document.getElementById('mobile-status-text').innerHTML = `<span style="color: var(--error); font-weight: 800;">❌ Conexão Perdida. Reconectando...</span>`;
        setTimeout(connectMobileMicrophoneWebSocket, 3000);
    };
}
