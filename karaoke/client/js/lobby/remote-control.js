// Controle da sala pelo celular, lado da TV (servidor: server/remote_control.py).
//
// A TV continua dona da partida: o celular manda um comando (`remote`), o
// servidor confere as travas (música tocando, GPU ocupada) e a TV executa com
// as mesmas funções dos botões dela. A cada mudança a TV publica o lobby
// (`lobby_state`: música da vez, cantores, ajustes, tela), que o servidor
// espelha para os celulares.
import { state } from '../core/state.js';
import { dom } from '../core/dom.js';
import { myRole } from '../core/config.js';
import { availableMics, renderLobby } from './lobby.js';
import { stopAutoNext } from './requests.js';
import { changeTranspose, changeSpeed, togglePause, setScoreMode, currentScoringMode, SPEED_STEP } from '../game/controls.js';

const PUBLISH_DEBOUNCE_MS = 150;
const PLAYING_SCREENS = ['singing', 'scoring'];

function send(msg) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(msg));
        return true;
    }
    return false;
}

function isPlaying() {
    return PLAYING_SCREENS.indexOf(state.currentAppState) !== -1;
}

function songInfo(id) {
    if (!id) return null;
    const song = (state.allSongs || []).find((s) => s.id === id);
    return song ? { id: song.id, title: song.title, artist: song.artist || '' } : { id, title: id, artist: '' };
}

function lobbyStateMessage() {
    return {
        type: 'lobby_state',
        screen: state.currentAppState,
        song: songInfo(state.remoteSongId),
        seats: (state.lobbySeats || []).map((s) => ({ mic: s.mic, team: s.team })),
        mics: availableMics(),
        turns: !!state.lobbyTurns,
        scoring_mode: currentScoringMode(),
        transpose: state.currentTranspose || 0,
        speed: state.currentSpeed || 1,
        paused: isPlaying() && !!dom.audioPlayer && dom.audioPlayer.paused,
    };
}

// Várias mudanças seguidas (renderLobby, troca de tela) viram uma mensagem só
export function publishLobbyState() {
    if (myRole !== 'display') return;
    clearTimeout(state.lobbyPublishTimer);
    state.lobbyPublishTimer = setTimeout(() => send(lobbyStateMessage()), PUBLISH_DEBOUNCE_MS);
}

// Música pronta pelo id; a lista da TV pode ser de antes da música ficar pronta
async function findSong(id) {
    let song = (state.allSongs || []).find((s) => s.id === id);
    if (song || !id) return song || null;
    try {
        const resp = await fetch('/api/songs');
        state.allSongs = await resp.json();
    } catch (e) {
        return null;
    }
    song = state.allSongs.find((s) => s.id === id);
    return song && song.is_ready !== false ? song : null;
}

// Tela do fim de jogo: volta ao lobby (sem a contagem da próxima)
async function leaveGameOver() {
    if (state.currentAppState !== 'game-over') return;
    stopAutoNext();
    await state.resetGameFn();
}

async function openSong(song) {
    await leaveGameOver();
    if (state.currentAppState !== 'waiting' || state.selectedSongId !== song.id) state.selectSongFn(song);
}

async function startFromRemote(reply, from) {
    const song = await findSong(state.remoteSongId);
    if (!song) return reply('Escolha uma música.');
    await openSong(song);
    if (!state.lobbySeats.length) return reply('Adicione pelo menos um cantor.');
    if (state.gpuBlock) return reply(`GPU ocupada: gerando a letra de ${state.gpuBlock}.`);
    // o aviso da 1ª partida pede um clique na TV: quem usa o celular não está lá
    try { localStorage.setItem('karaoke_onboarding_seen', 'true'); } catch (e) { }
    state.remoteStartFrom = from;
    dom.btnStart.click();
}

export async function handleRemote(cmd) {
    const reply = (message) => send({ type: 'remote_reply', to: cmd.from, message });
    // o servidor já barra, mas a TV pode estar no meio de uma troca de tela
    if (isPlaying() && ['select_song', 'seats', 'turns', 'scoring_mode', 'start'].indexOf(cmd.action) !== -1) {
        return reply('Espere a música acabar.');
    }
    switch (cmd.action) {
        case 'select_song': {
            const song = await findSong(cmd.song_id);
            if (!song) return reply('Música não encontrada.');
            await openSong(song);
            break;
        }
        case 'seats': {
            const valid = availableMics();
            state.lobbySeats = (cmd.seats || []).filter((s) => valid.indexOf(s.mic) !== -1);
            renderLobby();
            break;
        }
        case 'turns':
            state.lobbyTurns = !!cmd.value;
            renderLobby();
            break;
        case 'scoring_mode':
            setScoreMode(cmd.value);
            break;
        case 'transpose':
            changeTranspose(cmd.delta);
            break;
        case 'speed':
            changeSpeed(cmd.delta * SPEED_STEP);
            break;
        case 'pause':
            if (isPlaying()) togglePause();
            break;
        case 'stop':
            if (isPlaying()) {
                // encerra sem placar e deixa a mesma música no lobby
                const song = await findSong(state.remoteSongId);
                await state.resetGameFn();
                if (song) state.selectSongFn(song);
            }
            break;
        case 'start':
            await startFromRemote(reply, cmd.from);
            break;
        default:
            break;
    }
    publishLobbyState();
}

// Troca de tela (lobby, partida, fim de jogo): os celulares acompanham
export function initRemoteControl() {
    if (myRole !== 'display') return;
    state.publishLobbyState = publishLobbyState;
    const app = document.getElementById('app');
    if (app && window.MutationObserver) {
        new MutationObserver(publishLobbyState).observe(app, { attributes: true, attributeFilter: ['data-state'] });
    }
}
