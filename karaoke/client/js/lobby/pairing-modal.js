// Modal de pareamento: QR Code e link para o celular entrar como microfone.
import { activeRoomId } from '../config.js';
import { openModal, closeModal } from '../modal.js';
import { resolvePublicOrigin } from '../public-origin.js';

export function initPairingModal() {
    const pairingModal = document.getElementById('pairing-modal');
    const btnOpenPairing = document.getElementById('btn-open-pairing');
    const btnClosePairing = document.getElementById('btn-close-pairing');
    const pairingQrcode = document.getElementById('pairing-qrcode');
    const pairingLink = document.getElementById('pairing-link');

    if (!btnOpenPairing) return;

    btnOpenPairing.onclick = async () => {
        openModal(pairingModal);
        pairingModal.setAttribute('data-qrcode-status', 'loading');
        const qrLoading = document.getElementById('pairing-qrcode-loading');
        if (qrLoading) qrLoading.textContent = 'Gerando QR Code...';

        // Reset pairing status and dot indicator
        const pairingStatusText = document.getElementById('pairing-status-text');
        const statusBox = document.getElementById('pairing-status-box');
        if (pairingStatusText) {
            pairingStatusText.innerText = "Aguardando conexão do celular...";
        }
        if (statusBox) {
            statusBox.removeAttribute('data-status');
        }

        const pairingUrl = `${await resolvePublicOrigin()}/?role=mic&room=${activeRoomId}`;
        pairingLink.href = pairingUrl;
        pairingLink.innerText = pairingUrl;

        pairingQrcode.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(pairingUrl)}`;

        pairingQrcode.onload = () => {
            pairingModal.setAttribute('data-qrcode-status', 'ready');
        };
        // QR vem de um serviço externo: sem internet, fica só o link
        pairingQrcode.onerror = () => {
            pairingModal.setAttribute('data-qrcode-status', 'error');
            const loading = document.getElementById('pairing-qrcode-loading');
            if (loading) loading.textContent = 'QR indisponível · use o link';
        };
    };

    btnClosePairing.onclick = () => closeModal(pairingModal);

    // Abre o modal de pareamento ao clicar no QR Code ao lado de qualquer slot de jogador
    document.querySelectorAll('.btn-qr-pairing').forEach(btn => {
        btn.onclick = () => btnOpenPairing.click();
    });
}
