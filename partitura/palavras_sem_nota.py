"""Nota pra palavra cantada que o detector de melodia não pegou.

Caso típico: a primeira palavra do verso ("Pensem" em Rosa de Hiroshima) entra com ataque
soprado ou baixo e o detector só começa a nota na sílaba seguinte. A sílaba fica sem nota:
longe de qualquer nota ela some da partitura, perto ela gruda na nota vizinha.

Regra, antes da quantização e só com evidência:
- a palavra tem tempo (Whisper ou alinhamento) e nenhuma nota cobre esse tempo;
- há voz de verdade nesse trecho (energia da voz separada perto do volume cantado da
  música), senão é alucinação da transcrição e não ganha nota;
- a altura vem dos quadros do detector no trecho da palavra, aceitando confiança menor
  que a usada nas notas normais; trazida pra oitava das notas vizinhas. Sem quadros
  confiáveis, usa a nota cantada seguinte (até 1 s depois) ou a anterior;
- a nota nova vai do início da palavra até o fim dela ou até a próxima nota, sem
  sobrepor nenhuma nota existente.

Sem LLM: só os quadros do detector, energia e tempo das palavras.
"""
from __future__ import annotations

import numpy as np

PASSO_S = .01            # quadros do detector (10 ms)
PER_MIN = .20            # confiança mínima dos quadros (notas normais usam .45)
DB_VOZ = -32.0           # energia mínima relativa ao percentil 95 da voz
FRACAO_VOZ = .35         # fração do trecho com voz pra aceitar a palavra
VIZINHA_S = 1.0          # nota vizinha usada como referência de altura/oitava
DUR_MIN_S = .10
FOLGA_S = .02
ATAQUE_S = .15           # nota que começa até aqui depois do início da palavra cobre o ataque


def _cobertas(palavra, notas):
    """O ataque da palavra tem nota (a 2ª sílaba ter nota não basta: é o caso do "Pensem")."""
    ini = palavra[0]
    return any(a <= ini + ATAQUE_S and b > ini + FOLGA_S for a, b, _ in notas)


def _vizinhas(notas, ini, fim):
    ant = [n for n in notas if n[1] <= ini + FOLGA_S and ini - n[1] <= VIZINHA_S]
    seg = [n for n in notas if n[0] >= fim - FOLGA_S and n[0] - fim <= VIZINHA_S]
    return (ant[-1] if ant else None), (seg[0] if seg else None)


def _altura_dos_quadros(quadros, ini, fim, ref):
    if not quadros:
        return None, "sem quadros"
    a, b = int(ini / PASSO_S), int(np.ceil(fim / PASSO_S))
    midi = np.asarray(quadros["midi"][a:b], dtype=float)
    per = np.asarray(quadros["per"][a:b], dtype=float)
    db = np.asarray(quadros["db"][a:b], dtype=float)
    if not len(midi):
        return None, "sem quadros"
    voz = db > DB_VOZ
    if voz.mean() < FRACAO_VOZ:
        return False, "sem voz"
    ok = voz & (per >= PER_MIN) & (midi > 20)
    if ok.sum() < 3:
        return None, "altura incerta"
    m = float(np.median(midi[ok]))
    if ref is not None and abs(ref - m) >= 9:  # erro de oitava do detector em ataque fraco;
        m += 12 * round((ref - m) / 12)        # salto de quinta/sexta é música, fica
    return int(round(m)), "quadros"


def notas_para_palavras(notas, palavras, quadros=None):
    """Devolve (notas com as criadas, lista do que foi criado/recusado)."""
    notas = sorted(notas)
    novas, log = [], []
    for ini, fim, txt in sorted(palavras):
        if _cobertas((ini, fim), notas + novas):
            continue
        todas = sorted(notas + novas)
        inicio = max([ini] + [b for a, b, _ in todas if a < ini + FOLGA_S and b <= fim])
        prox = [a for a, _, _ in todas if a > inicio + FOLGA_S]
        fim = max(fim, inicio + DUR_MIN_S)
        final = min([fim] + prox) if prox else fim
        if final - inicio < DUR_MIN_S:
            # palavra curta espremida: estende até a próxima nota, se couber
            final = min(prox) if prox and min(prox) - inicio >= DUR_MIN_S else inicio
        if final - inicio < DUR_MIN_S:
            log.append(dict(palavra=txt, ini=round(ini, 3), criada=False, motivo="sem espaço"))
            continue
        ant, seg = _vizinhas(notas, inicio, final)
        ref = np.mean([n[2] for n in (ant, seg) if n is not None]) if (ant or seg) else None
        altura, origem = _altura_dos_quadros(quadros, inicio, final, ref)
        if altura is False:
            log.append(dict(palavra=txt, ini=round(ini, 3), criada=False, motivo=origem))
            continue
        if altura is None:
            if quadros and origem == "altura incerta" and not (ant or seg):
                log.append(dict(palavra=txt, ini=round(ini, 3), criada=False, motivo=origem))
                continue
            if seg is not None:
                altura, origem = seg[2], "nota seguinte"
            elif ant is not None:
                altura, origem = ant[2], "nota anterior"
            else:
                log.append(dict(palavra=txt, ini=round(ini, 3), criada=False, motivo="sem referência"))
                continue
        nota = (round(inicio, 3), round(final, 3), int(altura))
        novas.append(nota)
        log.append(dict(palavra=txt, ini=nota[0], fim=nota[1], midi=nota[2], criada=True, origem=origem))
    return sorted(notas + novas), log


def quadros_do_detector(midi, per, db):
    """Quadros (10 ms) guardados no diagnóstico: altura, confiança e energia relativa."""
    db, per = np.asarray(db, dtype=float), np.asarray(per, dtype=float)
    # volume cantado: só nos quadros com voz confiante (a música pode ter muito instrumental)
    cantado = db[per > .45]
    ref = float(np.percentile(cantado if len(cantado) >= 50 else db, 95))
    return dict(midi=np.round(midi, 2).tolist(), per=np.round(per, 3).tolist(),
                db=np.round(np.asarray(db) - ref, 1).tolist())
