"""Limpeza pra melodia ficar reconhecível (revisão do usuário, 2026-11-10). Determinístico, sem LLM.

- melodia_no_topo: enquanto a nota cantada soa, nenhuma nota do acompanhamento (direita ou
  esquerda) fica acima dela ou colada nela (até 2 semitons abaixo) — é aí que a melodia some;
- tirar_bordaduras: A–B–A com B curto e sem sílaba, a um tom ou menos de A, é tremida do
  detector (vibrato, deslize): B vira A e a nota fica sustentada;
- juntar_repetidas_esquerda: a mesma nota/acorde repetido colado na esquerda (Si♭ Si♭ Si♭ em
  colcheias) vira uma nota segurada dentro do meio compasso.
Eventos do gerar.py: (offset_em_tempos, duração, [midis], *resto); resto[0] = sílaba.
Notas da melodia em quantizar_melodia: (ini_t, fim_t, midi, ini_s, fim_s).
"""
from __future__ import annotations

import metrica

EPS = 1e-6


def tirar_bordaduras(notas_q, letras, max_tempos=0.5, max_salto=2):
    """Devolve (notas_q, quantas). letras: {índice: sílabas} — o índice não muda (só a altura)."""
    saida = [tuple(n) for n in notas_q]
    feitas = 0
    for i in range(1, len(saida) - 1):
        a, b, c = saida[i - 1], saida[i], saida[i + 1]
        if letras.get(i):
            continue
        colada = abs(a[1] - b[0]) < EPS and abs(b[1] - c[0]) < EPS
        if colada and a[2] == c[2] != b[2] and abs(b[2] - a[2]) <= max_salto and (b[1] - b[0]) <= max_tempos + EPS:
            saida[i] = (b[0], b[1], a[2], *b[3:])
            feitas += 1
    return saida, feitas


def juntar_repetidas_esquerda(me, janela=None):
    # meio compasso no 4/4; no 3/4 o compasso inteiro (mínima pontuada), senão a nota junta atravessa a barra
    janela = janela or (2.0 if metrica.TEMPOS == 4 else float(metrica.TEMPOS))
    saida = []
    for ev in sorted(me, key=lambda e: e[0]):
        off, dur, ps = ev[0], ev[1], sorted(ev[2])
        ant = saida[-1] if saida else None
        if (ant and ps and sorted(ant[2]) == ps and abs(ant[0] + ant[1] - off) < EPS
                and int((ant[0] + EPS) // janela) == int((off + EPS) // janela)):
            saida[-1] = (ant[0], ant[1] + dur, ant[2], *ant[3:])
        else:
            saida.append((off, dur, ps, *ev[3:]))
    return saida


def melodia_no_topo(md, me, folga=2):
    """Tira do acompanhamento as notas acima da nota cantada (ou coladas nela) enquanto ela soa.

    Devolve (md, me, quantas notas saíram)."""
    cantadas = [(e[0], e[0] + e[1], max(e[2])) for e in md if e[2] and len(e) > 3 and e[3]]
    if not cantadas:
        return md, me, 0
    cantadas.sort()
    inis = [c[0] for c in cantadas]
    from bisect import bisect_right

    def teto(off, fim):
        """Menor nota cantada que soa no trecho [off, fim)."""
        i = bisect_right(inis, fim - EPS)
        alturas = [p for a, b, p in cantadas[max(0, i - 8):i] if a < fim - EPS and b > off + EPS]
        return min(alturas) if alturas else None

    tiradas = 0
    novo_md = []
    for ev in md:
        if len(ev) > 3 and ev[3]:            # a própria nota cantada (e o que foi posto embaixo dela)
            novo_md.append(ev)
            continue
        t = teto(ev[0], ev[0] + ev[1])
        if t is None:
            novo_md.append(ev)
            continue
        ps = [q for q in ev[2] if q < t - folga]
        tiradas += len(ev[2]) - len(ps)
        if ps:
            novo_md.append((ev[0], ev[1], ps, *ev[3:]))
    novo_me = []
    for ev in me:
        t = teto(ev[0], ev[0] + ev[1])
        ps = list(ev[2]) if t is None else [q for q in ev[2] if q < t - folga]
        tiradas += len(ev[2]) - len(ps)
        if ps:
            novo_me.append((ev[0], ev[1], ps, *ev[3:]))
    return novo_md, novo_me, tiradas
