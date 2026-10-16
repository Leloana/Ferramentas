export const urlParams = new URLSearchParams(window.location.search);

let _roomId = localStorage.getItem('karaoke_room_id');
if (!_roomId) {
    _roomId = Math.floor(1000 + Math.random() * 9000).toString();
    localStorage.setItem('karaoke_room_id', _roomId);
}
export const activeRoomId = _roomId;
export const myRoom = urlParams.get('room') || activeRoomId;

// Código de fechamento do servidor quando outra tela assume a sala (ws/room.py):
// quem recebe não tenta reconectar, senão as duas telas se derrubam em loop.
export const DISPLAY_REPLACED_CODE = 4001;
// Celular: o mesmo aparelho reconectou em outra conexão e retomou o apelido.
export const MIC_REPLACED_CODE = 4002;
// Conexão velha da mesma tela (ou trocada pela nova dela): só não reconecta.
export const DISPLAY_STALE_CODE = 4003;
// Nome de sala já usado pela tela de outro aparelho.
export const ROOM_TAKEN_CODE = 4004;

// Celular-microfone: apelido lembrado e id do aparelho. Se a página recarregar ou
// a conexão cair, o celular entra sozinho de novo com o mesmo nome (mobile/mic-messages.js).
// A TV usa o mesmo id para o servidor saber que duas conexões são da mesma tela.
const MIC_NAME_KEY = 'karaoke_mic_name';
const MIC_DEVICE_KEY = 'karaoke_mic_device';

export function savedMicName() {
    try { return localStorage.getItem(MIC_NAME_KEY) || ''; } catch (e) { return ''; }
}

export function saveMicName(name) {
    try {
        if (name) localStorage.setItem(MIC_NAME_KEY, name);
        else localStorage.removeItem(MIC_NAME_KEY);
    } catch (e) { /* sem storage: só não lembra */ }
}

export function deviceId() {
    try {
        let id = localStorage.getItem(MIC_DEVICE_KEY);
        if (!id) {
            id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
            localStorage.setItem(MIC_DEVICE_KEY, id);
        }
        return id;
    } catch (e) {
        return '';
    }
}

// Navegador de TV (Tizen, webOS, Android TV, Fire TV...) ou forçado com ?tv=1.
// Liga a navegação por controle remoto com letras maiores (tv-nav.js / tv.css).
// TV Bro e outros navegadores da Google TV se identificam como celular Android:
// Android sem tela de toque é TV. ?tv=1 / ?tv=0 fica lembrado neste aparelho.
const TV_UA = /SMART-TV|Smart ?TV|Tizen|Web0S|webOS\.TV|NetCast|HbbTV|BRAVIA|AFT[A-Z]|CrKey|Chromecast|GoogleTV|Google TV|Android ?TV|TV ?Bro|VIDAA|Viera|Roku/i;
const androidWithoutTouch = /Android/i.test(navigator.userAgent) &&
    !(navigator.maxTouchPoints > 0) && !('ontouchstart' in window);

function tvOverride() {
    const q = urlParams.get('tv');
    try {
        if (q === '1' || q === '0') localStorage.setItem('karaoke_tv', q);
        return localStorage.getItem('karaoke_tv');
    } catch (e) {
        return q;
    }
}

const _tvOverride = tvOverride();
export const isTvBrowser = _tvOverride === '1' ||
    (_tvOverride !== '0' && (TV_UA.test(navigator.userAgent) || androidWithoutTouch));

// Três modos de aparelho: 'tv' (controle remoto, música sem Web Audio, letra a
// ~15 quadros/s), 'mobile' (celular/tablet) e 'desktop'. Vai para <html data-device>.
export const deviceKind = isTvBrowser ? 'tv' :
    ((/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768) ? 'mobile' : 'desktop');

// Papel deste aparelho: 'mic' (celular-microfone), 'display' (TV, PC ou celular no
// modo Sala) ou 'entry': celular aberto sem papel nem sala escolhe Jogador / Sala
// (mobile/entry.js). Link com ?room= sem papel continua abrindo a tela, como antes.
export const myRole = urlParams.get('role') ||
    (deviceKind === 'mobile' && !urlParams.get('room') ? 'entry' : 'display');

export const isSoloMobileMode = (myRole === 'display') && deviceKind === 'mobile';

// Ordem das conexões de tela desta página: o servidor descarta a mais velha
// quando ela chega depois da nova (lobby cancelado no INICIAR × jogo).
const displaySeq = { last: 0 };
export function displaySocketParams() {
    displaySeq.last = Math.max(Date.now(), displaySeq.last + 1);
    return `device=${encodeURIComponent(deviceId())}&seq=${displaySeq.last}`;
}

// Tela de entrada do celular: último modo (Jogador / Sala), nome da sala e a última
// sala em que entrou como jogador. O apelido é o mesmo do microfone (savedMicName).
const ENTRY_KEY = 'karaoke_entry';

export function savedEntry() {
    try {
        const raw = JSON.parse(localStorage.getItem(ENTRY_KEY) || '{}');
        return raw && typeof raw === 'object' ? raw : {};
    } catch (e) {
        return {};
    }
}

export function saveEntry(changes) {
    try {
        localStorage.setItem(ENTRY_KEY, JSON.stringify(Object.assign(savedEntry(), changes)));
    } catch (e) { /* sem storage: só não lembra */ }
}
