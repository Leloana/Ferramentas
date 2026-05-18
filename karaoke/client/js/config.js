export const urlParams = new URLSearchParams(window.location.search);
export const myRole = urlParams.get('role') || 'display';

let _roomId = localStorage.getItem('karaoke_room_id');
if (!_roomId) {
    _roomId = Math.floor(1000 + Math.random() * 9000).toString();
    localStorage.setItem('karaoke_room_id', _roomId);
}
export const activeRoomId = _roomId;
export const myRoom = urlParams.get('room') || activeRoomId;

export const isSoloMobileMode = (myRole === 'display') &&
    (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768);
