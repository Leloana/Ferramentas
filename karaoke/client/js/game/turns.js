// Revezar versos (duelo): cada verso com letra é de um time, em rodízio.
// Mesma regra do servidor (ws/room.py `turn_owner`): o k-ésimo verso com letra
// é do time k % n; versos sem letra (instrumental) ou só de voz de apoio não são de ninguém.
import { hasLeadVocals } from './backing-vocals.js';

export function turnOwner(segments, turnOrder, idx) {
    if (!turnOrder || turnOrder.length < 2 || !segments || !segments[idx]) return null;
    if (!hasLeadVocals(segments[idx].lyrics)) return null;
    let k = 0;
    for (let i = 0; i < idx; i++) {
        if (hasLeadVocals(segments[i].lyrics)) k++;
    }
    return turnOrder[k % turnOrder.length];
}
