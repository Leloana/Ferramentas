export const urlParams = new URLSearchParams(window.location.search);
export const myRole = urlParams.get('role') || 'display';

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

// Celular-microfone: apelido lembrado e id do aparelho. Se a página recarregar ou
// a conexão cair, o celular entra sozinho de novo com o mesmo nome (mobile/mic-messages.js).
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

export function micDeviceId() {
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

export const isSoloMobileMode = (myRole === 'display') && deviceKind === 'mobile';
