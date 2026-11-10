"""Níveis de dificuldade da partitura: fácil, médio, difícil.

| | fácil | médio | difícil |
|---|---|---|---|
| ritmo (grade) | semínima | colcheia | semicolcheia |
| mão esquerda (Acordes) | só o baixo, segurado | baixo + 3ª e 7ª | baixo + acorde em ritmo |
| Pop2Piano / Híbrido | 1 nota por mão | até 2 (esq.) / 3 (dir.) | completo |
| cifra | só tríades | completa | completa |
| tom | transposto pra tom sem acidentes | original | original |
"""
from __future__ import annotations

import numpy as np

NIVEIS = ("facil", "medio", "dificil")
NOME = {"facil": "Facil", "medio": "Medio", "dificil": "Dificil"}
GRADE = {"facil": 1, "medio": 2, "dificil": 4}  # subdivisões por tempo

# tétrade -> tríade (pra cifra fácil)
TRIADE = {"maj": "maj", "6": "maj", "7": "maj", "maj7": "maj",
          "m": "m", "m6": "m", "m7": "m", "m7b5": "m", "dim7": "m"}


def cifras_do_nivel(cifras, nivel):
    if nivel != "facil":
        return cifras
    saida, anterior = [], None
    for off, r, tipo in cifras:
        t = TRIADE.get(tipo, tipo)
        if (r, t) != anterior:
            saida.append((off, r, t))
        anterior = (r, t)
    return saida


def mao_esquerda_acordes(acs, nivel, fim, tipos, janela=2):
    """Mão esquerda gerada a partir dos acordes detectados."""
    ev = []
    blocos = [(j, r, t) for j, r, t, _ in acs if r is not None and j <= fim]
    if nivel == "facil":
        # só a fundamental (C3..B3), segurada enquanto o acorde não muda (até 4 tempos)
        i = 0
        while i < len(blocos):
            j, r, t = blocos[i]
            k = i + 1
            while k < len(blocos) and blocos[k][1] == r and blocos[k][0] == blocos[k - 1][0] + janela:
                k += 1
            dur = blocos[k - 1][0] + janela - j
            pos = j
            while dur > 0:
                d = min(4, dur)
                ev.append((pos, d, [48 + r % 12 if r % 12 < 8 else 36 + r % 12]))
                pos += d
                dur -= d
            i = k
        return ev
    for j, r, t in blocos:
        ints = tipos[t][0]
        raiz = 40 + (r - 4) % 12
        tons = [(r + ints[1]) % 12, (r + ints[-1]) % 12] if len(ints) == 4 else [(r + x) % 12 for x in ints[1:]]
        sup = sorted(52 + (pc - 4) % 12 for pc in tons)
        if nivel == "medio":
            # acorde fechado dentro de 1 oitava (baixo entre G2 e F#3 + 3ª/7ª logo acima): a análise mostrou
            # 64% de aberturas > oitava no voicing antigo (baixo e 3ª/7ª em oitavas separadas)
            baixo = 43 + (r - 7) % 12
            ev.append((j, janela, [baixo] + sorted(baixo + (pc - baixo) % 12 for pc in tons)))
        else:  # difícil: baixo no 1, acorde no 2 (padrão de "comping")
            ev.append((j, 1, [raiz]))
            ev.append((j + 1, janela - 1, sup + ([raiz + 19] if len(ints) == 3 else [])))
    return ev


def reduzir_mao(ev, nivel, mao):
    """Simplifica eventos polifônicos (Pop2Piano): limita notas por acorde.
    Mão direita guarda as de cima (melodia), esquerda as de baixo (baixo)."""
    if nivel == "dificil":
        return ev
    maximo = 1 if nivel == "facil" else (3 if mao == "direita" else 2)
    saida = []
    for off, dur, ps, *resto in ev:
        ps = sorted(ps)
        if len(ps) > maximo:
            if maximo == 1:
                ps = [ps[-1]] if mao == "direita" else [ps[0]]
            elif mao == "direita":
                ps = ps[-maximo:]
            else:
                ps = [ps[0], ps[-1]]
        saida.append((off, dur, ps, *resto))
    return saida


def transpor_facil(md_ev, me_ev, cifras):
    """Semitons pra levar a melhor armadura única da música pra zero acidentes (Dó maior / Lá menor).
    Armadura com s sustenidos tem tônica 7·s; transpor k soma 7·k ⇒ k ≡ -7·s (mod 12)."""
    import gerar
    eventos = [(d, ps) for _, d, ps, *_ in md_ev] + [(0.3 * d, ps) for _, d, ps, *_ in me_ev]
    s = gerar.escolher_armadura(eventos)
    k = (-7 * s) % 12
    if k > 6:
        k -= 12
    return md_ev, me_ev, cifras, k
