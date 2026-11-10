"""Acompanhamento da música inteira no teor escolhido (versão Acordes). Sem LLM.

Reaproveita as texturas da introdução gerada (introducao.mao_esquerda), aprovadas na
avaliação: calma/lenta acordes longos, emotiva arpejo, animada baixo-acorde, épica oitavas.
Regras:
- os acordes são os detectados na música (janelas de 2 tempos), sem trocar a harmonia;
- compasso com melodia densa (muitas notas cantadas por tempo) usa a textura um nível
  abaixo (difícil -> médio, médio -> fácil): o acompanhamento não compete com a voz; em
  compasso sem canto entra a textura completa do nível;
- janela sem acorde detectado fica sem acompanhamento (pausa), como hoje;
- calma, lenta e emotiva levam pedal trocando a cada acorde.
A correção das mãos, a harmonia contra a voz e os dedos rodam depois, como no resto.
"""
from __future__ import annotations

from introducao import COM_PEDAL, GRADE, _quantizar, mao_esquerda

ABAIXO = {"dificil": "medio", "medio": "facil", "facil": "facil"}
# notas cantadas por tempo a partir das quais o compasso é "denso"
DENSO = {"facil": 1.0, "medio": 1.5, "dificil": 2.0}
EPS = 1e-6


def densidade_por_compasso(md_ev):
    """{compasso: notas cantadas por tempo} (4/4)."""
    cont = {}
    for o, d, ps, *_ in md_ev:
        cont[int(o // 4)] = cont.get(int(o // 4), 0) + 1
    return {c: n / 4 for c, n in cont.items()}


def trechos_de_acorde(acs, fim, janela=2):
    """[(inicio, fim, raiz, tipo)] juntando janelas iguais seguidas; None = sem acorde."""
    saida = []
    for j, r, t, *_ in acs:
        if j >= fim:
            break
        if r is None:
            continue
        if saida and saida[-1][2:] == (r, t) and abs(saida[-1][1] - j) < EPS:
            saida[-1] = (saida[-1][0], j + janela, r, t)
        else:
            saida.append((j, j + janela, r, t))
    return saida


def acompanhamento_no_teor(acs, md_ev, tipos, nivel, teor, fim, variacao=0, janela=2):
    """(eventos da esquerda, pedais [(ini, fim)], info). Offsets em tempos da música."""
    dens = densidade_por_compasso(md_ev)
    eventos, pedais = [], []
    rebaixados = 0
    for ini, fim_t, r, t in trechos_de_acorde(acs, fim, janela):
        fim_t = min(fim_t, fim)
        if teor in COM_PEDAL:
            pedais.append((ini, fim_t))
        # quebra o trecho nos compassos: cada compasso escolhe a textura pela densidade do canto
        pos = ini
        while pos < fim_t - EPS:
            compasso = int(pos // 4)
            ate = min(fim_t, 4.0 * (compasso + 1))
            nv = nivel
            if dens.get(compasso, 0) >= DENSO[nivel] - EPS:
                nv = ABAIXO[nivel]
                rebaixados += nv != nivel
            dur = ate - pos
            pedaco = mao_esquerda([(0.0, r, t)], dur, teor, nv, tipos, variacao)
            passo = 1.0 if nv == "facil" else GRADE[nv]
            for o, d, ps in _quantizar(pedaco, passo, dur):
                eventos.append((pos + o, d, ps))
            pos = ate
    eventos.sort(key=lambda e: e[0])
    info = dict(teor=teor, nivel=nivel, trechos=len(pedais) if pedais else None,
                compassos_simplificados_pelo_canto=rebaixados)
    return eventos, pedais, info
