import { state, setAppState } from './state.js';
import { iconSvg } from './icons.js';
import { myRoom } from './config.js';
import { showToast } from './toast.js';
import { dom } from './dom.js';
import { fillLine, setLyricsScriptAvailable } from './lyrics-script.js';
import { verseQuality, replayClass } from './verse-stamp.js';

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function connectMobileMicrophoneWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${myRoom}?role=mic`;

    state.mobileWs = new WebSocket(wsUrl);
    state.mobileWs.binaryType = 'arraybuffer';

    state.mobileWs.onopen = () => {
        document.getElementById('mobile-song-title').innerText = "Karaoke";
        document.getElementById('mobile-status-text').innerHTML = `Sala <span class="mic-status__name">${myRoom}</span>`;
    };

    const MIC_HANDLERS = {
        register_request(data, context) {
            const { dom } = context;
            setAppState('registering');
            if (dom.btnMobileRegister) {
                dom.btnMobileRegister.disabled = false;
                dom.btnMobileRegister.innerText = "Entrar";
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
            showToast(`Registrado como "${data.name}"`, "success");
            
            const statusText = document.getElementById('mobile-status-text');
            if (statusText) {
                statusText.innerHTML = `<span class="mic-status__name">${escapeHtml(data.name)}</span> · Sala ${myRoom}`;
            }
            
            setAppState('singing');
        },
        registration_error(data, context) {
            const { dom } = context;
            if (dom.btnMobileRegister) {
                dom.btnMobileRegister.disabled = false;
                dom.btnMobileRegister.innerText = "Entrar";
            }
            if (dom.mobileRegisterError) {
                dom.mobileRegisterError.innerText = data.message;
                dom.mobileRegisterError.setAttribute('data-visible', 'true');
            }
            showToast(data.message, "error");
        },
        game_started(data, context) {
            const { state } = context;
            const scoreLine = document.getElementById('mobile-score-text');
            if (scoreLine) scoreLine.hidden = true;
            const activePlayers = data.active_players || [];
            state.isActiveInGame = activePlayers.includes(state.mobileNickname);
            
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                lyrText.classList.remove('lyrics-line');
                if (state.isActiveInGame) {
                    lyrText.innerHTML = `<span class="mic-note mic-note--good">Você está no jogo</span>Prepare-se`;
                } else {
                    lyrText.innerHTML = `<span class="mic-note">Assistindo</span>Próxima rodada`;
                }
            }
        },
        pairing_status(data, context) {
            const { state, myRoom } = context;
            const statusText = document.getElementById('mobile-status-text');
            if (statusText) {
                if (data.status === 'paired') {
                    if (state.mobileNickname) {
                        statusText.innerHTML = `<span class="mic-status__name">${escapeHtml(state.mobileNickname)}</span> · Sala ${myRoom}`;
                    }
                } else if (data.status === 'unpaired') {
                    statusText.innerHTML = `<span class="mic-status--error">TV desconectada (sala ${myRoom})</span>`;
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
            if (lyrText) fillLine(lyrText, data.lyrics, data.lyrics_romaji);
            setLyricsScriptAvailable(data.lyrics_romaji);

            const songTitle = document.getElementById('mobile-song-title');
            if (songTitle && data.song_title) {
                songTitle.innerText = data.song_title;
            }
        },
        segment_result(data, context) {
            const { state } = context;
            // A nota chega quando o verso seguinte já começou: vai numa linha
            // própria para não apagar a letra que o cantor está acompanhando.
            const scoreLine = document.getElementById('mobile-score-text');
            if (!scoreLine) return;
            let myScore = data.score;
            let myTotalScore = data.total_score;

            if (state.isActiveInGame && data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname]) {
                const pData = data.player_scores[state.mobileNickname];
                myScore = pData.score;
                myTotalScore = pData.total_score;
            }

            const lastEl = document.getElementById('mobile-score-last');
            const quality = verseQuality(myScore);
            lastEl.textContent = `${quality.word} ${myScore}%`;
            lastEl.dataset.quality = quality.key;
            replayClass(lastEl, 'seg-score--pulse');
            document.getElementById('mobile-score-total').textContent = `${myTotalScore}%`;
            scoreLine.hidden = false;
        },
        outro_start(data, context) {
            const { state } = context;
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                lyrText.classList.remove('lyrics-line');
                if (state.isActiveInGame) {
                    lyrText.innerHTML = `${iconSvg('fermata')} Fim da música<span class="mic-note">Calculando o placar</span>`;
                } else {
                    lyrText.innerHTML = `${iconSvg('double-bar')} Fim da música<span class="mic-note">Calculando o placar</span>`;
                }
            }
        },
        game_over(data, context) {
            const { state } = context;
            const scoreLine = document.getElementById('mobile-score-text');
            if (scoreLine) scoreLine.hidden = true;
            const lyrText = document.getElementById('mobile-lyrics-text');
            if (lyrText) {
                lyrText.classList.remove('lyrics-line');
                let myTotalScore = data.total_score;
                if (data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname] !== undefined) {
                    myTotalScore = data.player_scores[state.mobileNickname];
                }
                
                let html = `<div class="mic-final">`;
                html += `<span class="mic-final__title">Placar final</span>`;
                
                if (state.isActiveInGame) {
                    html += `<span class="mic-final__avg">Sua média: <strong>${myTotalScore.toFixed(1)}%</strong></span>`;
                }
                
                if (data.player_scores && Object.keys(data.player_scores).length > 0) {
                    html += `<div class="mic-final__list">`;
                    const sortedPlayers = Object.entries(data.player_scores).sort((a, b) => b[1] - a[1]);
                    sortedPlayers.forEach(([name, score], idx) => {
                        const medal = `<span class="place-num">${idx + 1}º</span>`;
                        const displayName = name === "PC_Local" ? "Mic do dispositivo" : name;
                        const isMe = name === state.mobileNickname;
                        html += `<div class="mic-final__row${isMe ? ' mic-final__row--me' : ''}">`;
                        html += `<span>${medal} ${escapeHtml(displayName)}</span>`;
                        html += `<span>${score.toFixed(1)}%</span>`;
                        html += `</div>`;
                    });
                    html += `</div>`;
                } else if (!state.isActiveInGame) {
                    html += `<span class="mic-note">Placar na TV</span>`;
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
        document.getElementById('mobile-status-text').innerHTML = `<span class="mic-status--error">Conexão perdida. Reconectando...</span>`;
        setTimeout(connectMobileMicrophoneWebSocket, 3000);
    };
}
