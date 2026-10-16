// Mensagens do servidor para o celular-microfone (WebSocket role=mic), uma
// função por tipo: entrada com apelido, letra do verso, nota e fim de jogo.
import { state, setAppState } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { myRoom, savedMicName, saveMicName, micDeviceId } from '../core/config.js';
import { showToast } from '../core/toast.js';
import { dom } from '../core/dom.js';
import { fillLine, setLyricsScriptAvailable } from '../game/lyrics-script.js';
import { verseQuality, replayClass } from '../game/verse-stamp.js';
import { escapeHtml } from '../core/html.js';
import { onRequestsUpdate } from '../lobby/requests.js';
import { onRemoteState } from './room-panel.js';
import { showMicGameOver, setFinalLayout } from './mic-final.js';
import { setMicStatus } from './mic-socket.js';
import { remindMicIfOff, setMicLocked, reportMicState } from './mobile-mic-view.js';
import { keepScreenOn } from '../core/wake-lock.js';
import { setReactionsVisible } from './reactions-bar.js';
import { COMBO_MIN } from '../game/combo.js';
import { fillTimedWords } from '../game/lyrics-carousel.js';
import { followVerse, stopFollowing, onSingingState } from './mic-words.js';

function setRegisterButton(busy) {
    if (!dom.btnMobileRegister) return;
    dom.btnMobileRegister.disabled = busy;
    dom.btnMobileRegister.innerText = busy ? "ENTRANDO..." : "Entrar";
}

function showNameInStatus(name) {
    setMicStatus(`<span class="mic-status__name">${escapeHtml(name)}</span> · Sala ${escapeHtml(myRoom)}`);
}

// Aviso no lugar da letra (fora do verso: entrada no jogo, fim da música)
function setLyricsNote(html) {
    const lyrText = document.getElementById('mobile-lyrics-text');
    if (!lyrText) return;
    stopFollowing();
    lyrText.classList.remove('lyrics-line');
    lyrText.innerHTML = html;
    const next = document.getElementById('mobile-lyrics-next');
    if (next) next.hidden = true;
    setLyricsLive(false);
}

// Caixa da letra acesa = hora de cantar este verso (singing_state do servidor)
function setLyricsLive(active) {
    const box = document.getElementById('mobile-lyrics-container');
    if (box) box.classList.toggle('is-live', !!active);
}

// Nota deste celular no verso: a própria em disputa, a geral no solo. null = o verso
// era de outro cantor (revezar versos): o servidor só manda a nota de quem cantou, e
// cair na geral mostrava a nota do outro ("falha 0%") como se fosse a deste celular.
function myVerseScore(data) {
    const scores = data.player_scores || {};
    const own = state.isActiveInGame && state.mobileNickname && scores[state.mobileNickname];
    if (own) return { score: own.score, total: own.total_score, pitch: own.pitch, combo: own.combo };
    const names = Object.keys(scores);
    if (state.isActiveInGame && names.length && names.indexOf('Solo') === -1) return null;
    return { score: data.score, total: data.total_score, pitch: data.pitch, combo: data.combo };
}

const MIC_HANDLERS = {
    register_request() {
        setAppState('registering');
        if (dom.mobileRegisterError) dom.mobileRegisterError.removeAttribute('data-visible');
        // Já entrou antes neste celular: entra sozinho com o mesmo apelido
        // (página recarregou, rede caiu). Se der erro, cai no formulário.
        const saved = savedMicName();
        if (saved && dom.mobileNicknameInput) dom.mobileNicknameInput.value = saved;
        if (saved && !state.micAutoRegisterFailed && state.mobileWs && state.mobileWs.readyState === WebSocket.OPEN) {
            state.micAutoRegistering = true;
            setRegisterButton(true);
            state.mobileWs.send(JSON.stringify({ type: "register_name", name: saved, device: micDeviceId() }));
            return;
        }
        setRegisterButton(false);
    },
    register_wait(data) {
        setAppState('waiting');
        if (dom.mobileQueuePosition) {
            dom.mobileQueuePosition.innerText = data.position;
        }
    },
    registration_success(data) {
        state.mobileNickname = data.name;
        saveMicName(data.name);
        const automatic = state.micAutoRegistering;
        state.micAutoRegistering = false;
        if (!automatic) showToast(`Registrado como "${data.name}"`, "success");
        showNameInStatus(data.name);
        setAppState('singing');
        reportMicState();  // a TV sabe de cara se este microfone está ligado
        // reconectou: as reações voltam só com o game_started da partida em andamento
        setReactionsVisible(false);
        // depois de recarregar a tela apagava antes do primeiro toque em LIGAR MIC
        keepScreenOn();
    },
    registration_error(data) {
        // a entrada automática falhou (apelido pego por outro aparelho): formulário
        if (state.micAutoRegistering) state.micAutoRegisterFailed = true;
        state.micAutoRegistering = false;
        setRegisterButton(false);
        if (dom.mobileRegisterError) {
            dom.mobileRegisterError.innerText = data.message;
            dom.mobileRegisterError.setAttribute('data-visible', 'true');
        }
        showToast(data.message, "error");
    },
    requests_update(data) {
        onRequestsUpdate(data.requests);
    },
    request_error(data) {
        showToast(data.message, 'error');
    },
    // aba Sala: estado da TV (música da vez, cantores, ajustes) e comando recusado
    remote_state(data) {
        onRemoteState(data);
    },
    remote_error(data) {
        showToast(data.message, 'error');
        onRemoteState(state.remoteState || {});
    },
    game_started(data) {
        setFinalLayout(false);
        const scoreLine = document.getElementById('mobile-score-text');
        if (scoreLine) scoreLine.hidden = true;
        const activePlayers = data.active_players || [];
        state.isActiveInGame = activePlayers.includes(state.mobileNickname);
        setLyricsNote(state.isActiveInGame
            ? `<span class="mic-note mic-note--good">Você está no jogo</span>Prepare-se`
            : `<span class="mic-note">Assistindo</span>Reaja na TV`);
        setReactionsVisible(!state.isActiveInGame);
        setMicLocked(!state.isActiveInGame);
        remindMicIfOff();
    },
    pairing_status(data) {
        if (data.status === 'paired') {
            if (state.mobileNickname) showNameInStatus(state.mobileNickname);
        } else if (data.status === 'unpaired') {
            setMicStatus(`<span class="mic-status--error">TV desconectada (sala ${escapeHtml(myRoom)})</span>`);
        }
    },
    singing_state(data) {
        state.isSingingActive = state.isActiveInGame ? data.active : false;
        setLyricsLive(data.active);
        onSingingState(data);
    },
    segment_start(data) {
        setFinalLayout(false);
        const lyrText = document.getElementById('mobile-lyrics-text');
        if (lyrText) {
            // palavra por palavra (acende como na TV); sem tempos, a linha inteira
            if (data.lyrics_timed && data.lyrics_timed.length) {
                followVerse(data, fillTimedWords(lyrText, data));
            } else {
                fillLine(lyrText, data.lyrics, data.lyrics_romaji);
                followVerse(data, null);
            }
            // verso comprido (rap): letra menor e a caixa rola, em vez de estourar a tela
            lyrText.classList.toggle('is-long', (data.lyrics || '').length > 70);
            const box = lyrText.parentElement;
            if (box) box.scrollTop = 0;
        }
        // próximo verso, menor: dá para se preparar sem olhar a TV
        const nextEl = document.getElementById('mobile-lyrics-next');
        if (nextEl) {
            fillLine(nextEl, data.next_lyrics, data.next_lyrics_romaji);  // segue original/romaji/ambos
            nextEl.hidden = !data.next_lyrics;
        }
        // revezar versos: "Sua vez" / "Vez de Ana"
        const turnEl = document.getElementById('mobile-turn');
        if (turnEl) {
            const turn = data.turn;
            const mine = turn && state.mobileNickname && turn.indexOf(state.mobileNickname) !== -1;
            turnEl.hidden = !turn;
            turnEl.dataset.mine = mine ? 'true' : 'false';
            turnEl.textContent = !turn ? '' : (mine ? 'Sua vez' : `Vez de ${turn.join(' + ')}`);
            // verso de outro cantor: a letra fica esmaecida
            const lyricsBox = document.getElementById('mobile-lyrics-container');
            if (lyricsBox) lyricsBox.classList.toggle('is-other-turn', !!turn && !mine);
        }
        setLyricsScriptAvailable(data.japanese_script);
    },
    segment_result(data) {
        // A nota chega quando o verso seguinte já começou: vai numa linha
        // própria para não apagar a letra que o cantor está acompanhando.
        const scoreLine = document.getElementById('mobile-score-text');
        if (!scoreLine) return;
        if (data.recalc) {
            // voltou a música: atualiza só a média geral
            const own = data.player_scores && state.mobileNickname && data.player_scores[state.mobileNickname];
            document.getElementById('mobile-score-total').textContent = `${own ? own.total_score : data.total_score}%`;
            return;
        }
        const mine = myVerseScore(data);
        if (!mine) return;  // verso do outro: fica a última nota deste cantor
        const lastEl = document.getElementById('mobile-score-last');
        const quality = verseQuality(mine.score);
        let text = typeof mine.pitch === 'number'
            ? `${quality.word} ${mine.score}% · tom ${Math.round(mine.pitch)}%`
            : `${quality.word} ${mine.score}%`;
        if (mine.combo >= COMBO_MIN) text += ` · combo ×${mine.combo}`;
        lastEl.textContent = text;
        lastEl.dataset.quality = quality.key;
        replayClass(lastEl, 'seg-score--pulse');
        document.getElementById('mobile-score-total').textContent = `${mine.total}%`;
        scoreLine.hidden = false;
    },
    outro_start() {
        const icon = iconSvg(state.isActiveInGame ? 'fermata' : 'double-bar');
        setLyricsNote(`${icon} Fim da música<span class="mic-note">Calculando o placar</span>`);
    },
    game_cancelled() {
        // a TV saiu da partida sem placar: quem esperava pode ligar o microfone
        state.isActiveInGame = false;
        state.isSingingActive = false;
        setReactionsVisible(false);
        setMicLocked(false);
        setLyricsNote(`<span class="mic-note">Partida encerrada</span>Aguardando a TV`);
    },
    game_over(data) {
        stopFollowing();
        setReactionsVisible(false);
        setMicLocked(false);
        showMicGameOver(data);
    },
    pong() {
        // resposta ao ping de mic-socket.js: só prova que a conexão está viva
    }
};

export function handleMicMessage(data) {
    const handler = MIC_HANDLERS[data.type];
    if (handler) {
        handler(data);
    } else {
        console.warn(`Tipo de mensagem de microfone desconhecido recebido: ${data.type}`);
    }
}
