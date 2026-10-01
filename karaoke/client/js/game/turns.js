// Revezar versos (duelo): cada verso com letra é de um time, em rodízio.
// Mesma regra do servidor (ws/room.py `turn_owner`): o k-ésimo verso com letra
// é do time k % n; versos sem letra (instrumental) não são de ninguém.
export function turnOwner(segments, turnOrder, idx) {
    if (!turnOrder || turnOrder.length < 2 || !segments || !segments[idx]) return null;
    if (!String(segments[idx].lyrics || '').trim()) return null;
    let k = 0;
    for (let i = 0; i < idx; i++) {
        if (String(segments[i].lyrics || '').trim()) k++;
    }
    return turnOrder[k % turnOrder.length];
}
