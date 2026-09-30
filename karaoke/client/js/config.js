export const urlParams = new URLSearchParams(window.location.search);
export const myRole = urlParams.get('role') || 'display';

let _roomId = localStorage.getItem('karaoke_room_id');
if (!_roomId) {
    _roomId = Math.floor(1000 + Math.random() * 9000).toString();
    localStorage.setItem('karaoke_room_id', _roomId);
}
export const activeRoomId = _roomId;
export const myRoom = urlParams.get('room') || activeRoomId;

// Navegador de TV (Tizen, webOS, Android TV, Fire TV...) ou forçado com ?tv=1.
// Liga a navegação por controle remoto com letras maiores (tv-nav.js / tv.css).
export const isTvBrowser = urlParams.get('tv') === '1' ||
    /SMART-TV|SmartTV|Tizen|Web0S|webOS\.TV|NetCast|HbbTV|BRAVIA|AFT[A-Z]|CrKey|GoogleTV|Android ?TV|VIDAA|Viera|Roku/i.test(navigator.userAgent);

export const isSoloMobileMode = (myRole === 'display') && !isTvBrowser &&
    (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768);
