// Modal "Cantores" (TV/PC): ranking → perfil. Voltar dentro do perfil volta
// para a lista; na lista, fecha.
import { openModal, closeModal } from './modal.js';
import { showToast } from './toast.js';
import { fetchPlayers, fetchProfile, renderPlayersList, renderProfile } from './profile-view.js';

export function initPlayersModal() {
    const modal = document.getElementById('players-modal');
    const openBtn = document.getElementById('btn-open-players');
    const view = document.getElementById('players-view');
    const title = document.getElementById('players-modal-title');
    const back = document.getElementById('btn-players-back');
    if (!modal || !openBtn || !view) return;

    const showList = async () => {
        modal.dataset.view = 'list';
        title.textContent = 'Cantores';
        view.replaceChildren();
        try {
            renderPlayersList(view, await fetchPlayers(), showProfile);
        } catch (e) {
            showToast(e.message, 'error');
        }
    };

    const showProfile = async (name) => {
        modal.dataset.view = 'profile';
        title.textContent = 'Perfil';
        try {
            renderProfile(view, await fetchProfile(name));
        } catch (e) {
            showToast(e.message, 'error');
        }
        const scroller = modal.querySelector('.modal-content');
        if (scroller) scroller.scrollTop = 0;
    };

    // Esc / Voltar da TV / botão do navegador: perfil → lista antes de fechar
    modal._onBack = () => {
        if (modal.dataset.view !== 'profile') return false;
        showList();
        return true;
    };

    openBtn.addEventListener('click', () => {
        openModal(modal);
        showList();
    });
    back.addEventListener('click', () => {
        if (!modal._onBack()) closeModal(modal);
    });
}

// Abre direto no perfil de alguém (ex.: tocar no nome no fim de jogo).
export function openPlayerProfile(name) {
    const openBtn = document.getElementById('btn-open-players');
    if (openBtn) openBtn.click();
    const modal = document.getElementById('players-modal');
    // a lista carrega primeiro; em seguida troca para o perfil
    setTimeout(() => {
        const row = Array.prototype.find.call(document.querySelectorAll('#players-view .player-row__name'),
            (n) => n.textContent === name);
        if (row) row.closest('button').click();
        else if (modal) modal.dataset.view = 'list';
    }, 250);
}
