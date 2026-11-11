"""Melodia no tom: afinação da gravação + notas duvidosas puxadas pra escala do trecho. Sem LLM.

Problema (revisão do usuário, 2026-11-10): a voz desliza, tem vibrato e a gravação pode não estar
em Lá = 440 Hz; arredondar a mediana de cada nota pro semitom mais perto, sem olhar o tom, fazia
"5 notas, 3 certas e 2 dissonâncias" (Don't Look Back in Anger: 27% das notas fora de Dó maior).

1. Afinação: desvio médio (circular) da voz em relação ao semitom, nos quadros confiantes; a
   altura de cada nota é medida já descontando esse desvio.
2. Tom: nota que cai fora da escala do trecho (armadura estimada pelos acordes em volta) e fora
   do acorde do momento vai pra nota vizinha da escala/acorde quando a altura cantada estava
   puxando pra ela, ou quando é curta (passagem/deslize). Cromatismo cantado de verdade (nota
   longa, bem no centro do semitom) fica.
Usa os quadros do detector guardados em cache/transcricao.json (diagnostico.quadros): funciona
com --reusar-cache, sem rodar o CREPE de novo.
"""
from __future__ import annotations

import numpy as np

PUXA = 0.20       # semitom: altura a pelo menos isto do centro, na direção da vizinha da escala
CURTA_S = 0.25    # nota fora do tom mais curta que isto é passagem: vai pra escala de qualquer jeito
LONGA_S = 0.60    # nota longa e centrada fora do tom é cromatismo de verdade: fica


def afinacao(quadros) -> float:
    """Desvio da voz em semitons (-0,5..0,5): positivo = gravação acima de Lá 440."""
    m = np.asarray(quadros["midi"], dtype=float)
    per = np.asarray(quadros["per"], dtype=float)
    db = np.asarray(quadros["db"], dtype=float)
    ok = (per > .7) & (db > -30) & (m > 30)
    if ok.sum() < 200:
        return 0.0
    ang = 2 * np.pi * (m[ok] - np.round(m[ok]))
    return float(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) / (2 * np.pi))


def altura(quadros, ini_s: float, fim_s: float, desvio: float) -> float | None:
    m = np.asarray(quadros["midi"][int(ini_s * 100):int(fim_s * 100)], dtype=float)
    per = np.asarray(quadros["per"][int(ini_s * 100):int(fim_s * 100)], dtype=float)
    bons = m[(per > .45) & (m > 30)]
    return float(np.median(bons)) - desvio if len(bons) else None


def _escala_local(acs, tipos, t, raio=8.0):
    from gerar import escolher_armadura
    from niveis import escala_da_armadura
    ev = [(1.0, [(r + i) % 12 + 48 for i in tipos[ti][0]]) for j, r, ti, *_ in acs
          if r is not None and abs(j - t) <= raio]
    return escala_da_armadura(escolher_armadura(ev)) if ev else None


def melodia_no_tom(notas, quadros, acs, tipos, pos):
    """notas: (ini_s, fim_s, midi). Devolve (notas, registro, desvio_em_cents)."""
    from niveis import notas_do_acorde
    if not quadros or "midi" not in quadros:
        return list(notas), [], 0
    desvio = afinacao(quadros)
    saida, registro = [], []
    for a, b, p in notas:
        h = altura(quadros, a, b, desvio)
        p0 = int(round(h)) if h is not None else int(p)
        h = p0 if h is None else h
        t = pos(a)
        escala = _escala_local(acs, tipos, t)
        permitidas = (escala or set()) | notas_do_acorde(acs, tipos, t)
        novo, motivo = p0, ("afinacao" if p0 != p else None)
        if escala and p0 % 12 not in permitidas:
            cands = [q for q in (p0 - 1, p0 + 1) if q % 12 in permitidas]
            if cands:
                q = min(cands, key=lambda q: abs(h - q))
                dur = b - a
                puxando = (h - p0) * (q - p0) >= PUXA          # desvio na direção da vizinha
                if dur < CURTA_S or (puxando and dur < LONGA_S) or (puxando and abs(h - p0) >= .35):
                    novo, motivo = q, "tom"
        if motivo:
            registro.append(dict(ini=round(a, 3), antes=int(p), depois=novo, altura=round(h, 2), motivo=motivo))
        saida.append((a, b, novo))
    return saida, registro, round(desvio * 100)
