// Combo na TV: versos "Na mosca" seguidos (o servidor conta, server/combo.py).
// Solo: selo no palco. Disputa: chip ×N na barra de cada cantor (no time, na
// linha do membro). Só aparece a partir do 2º verso seguido.
import { state } from '../core/state.js';
import { iconSvg } from '../core/icons.js';
import { replayClass } from './verse-stamp.js';

export const COMBO_MIN = 2;

const SLOTS = ['p1', 'p2', 'p3', 'p4'];

export function comboValue(result) {
    const n = result && parseInt(result.combo, 10);
    return n > 0 ? n : 0;
}

// Selo do palco (solo). quiet: recálculo depois de voltar a música, sem animar.
export function showStageCombo(n, quiet) {
    const badge = document.getElementById('combo-badge');
    if (!badge) return;
    if (n < COMBO_MIN) {
        badge.hidden = true;
        badge.dataset.n = '';
        return;
    }
    const grew = !quiet && badge.dataset.n !== String(n);
    badge.dataset.n = String(n);
    badge.innerHTML = `${iconSvg('flame')}<span>Combo</span><strong>×${n}</strong>`;
    badge.hidden = false;
    if (grew) replayClass(badge, 'combo-badge--up');
    else if (quiet) badge.classList.remove('combo-badge--up');
}

function chipIn(host, n) {
    let chip = host.querySelector('.mp-combo');
    if (n < COMBO_MIN) {
        if (chip) chip.remove();
        return;
    }
    const grew = !chip || chip.dataset.n !== String(n);
    if (!chip) {
        chip = document.createElement('span');
        chip.className = 'mp-combo';
        // logo depois do nome: na barra deitada o nome e a nota ficam nas pontas
        const name = host.querySelector('.mp-player-name');
        if (name) name.after(chip);
        else host.append(chip);
    }
    chip.dataset.n = String(n);
    chip.innerHTML = `${iconSvg('flame')}×${n}`;
    if (grew) replayClass(chip, 'mp-combo--up');
}

// playerScores: { microfone: { combo, ... } } do segment_result
export function showBarCombos(playerScores) {
    const groups = state.scoreGroups || [];
    groups.slice(0, SLOTS.length).forEach((group, idx) => {
        const bar = document.getElementById(`mp-score-bar-${SLOTS[idx]}`);
        if (!bar) return;
        if (group.mics.length === 1) {
            const info = bar.querySelector('.mp-score-info, .mp-score-info-vertical');
            if (info) chipIn(info, comboValue(playerScores[group.mics[0]]));
            return;
        }
        bar.querySelectorAll('.mp-member').forEach((row) => {
            const name = row.querySelector('.mp-member__name');
            if (name) chipIn(name, comboValue(playerScores[row.dataset.mic]));
        });
    });
}

export function clearCombos() {
    showStageCombo(0);
    document.querySelectorAll('.mp-combo').forEach((chip) => chip.remove());
}
