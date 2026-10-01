"""Combo: versos "Na mosca" seguidos de um cantor, na ordem dos versos."""
from __future__ import annotations

from collections.abc import Iterable

# mesma faixa do carimbo "Na mosca" (verse-stamp.js) e do "good" do cartão
COMBO_MIN_SCORE = 85


def combo_runs(scores: dict[int, float], verses: Iterable[int] = ()) -> tuple[int, int]:
    """(sequência que termina no último verso pontuado, maior sequência da partida).

    `verses`: versos já fechados para este cantor. Um deles sem nota quebra a
    sequência: ou ainda está no Whisper (o verso de vocalize, sem Whisper, chega
    antes do anterior) ou o celular não mandou áudio. Revezando versos, só entram
    os versos do próprio cantor.
    """
    if not scores:
        return 0, 0
    last = max(scores)
    current = best = 0
    for idx in sorted(set(scores) | {i for i in verses if i < last}):
        current = current + 1 if scores.get(idx, 0) >= COMBO_MIN_SCORE else 0
        best = max(best, current)
    return current, best
