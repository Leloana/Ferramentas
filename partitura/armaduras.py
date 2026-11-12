"""Armadura por trecho: troca só com modulação de verdade e em lugar de leitura natural.

Programação dinâmica sobre segmentos de blocos de 4 compassos:
- custo de cada armadura num bloco = peso das notas que ficariam com acidente + distância do
  tom provável (Krumhansl-Kessler: armadura do tom, não só a de menos acidentes);
- cada armadura dura pelo menos `min_blocos` blocos (16 compassos): passagem cromática,
  acorde emprestado ou ponte de 8 compassos não trocam a armadura;
- trocar no começo de frase da melodia (logo depois de pausa) custa `troca`, no meio da
  frase o dobro; a troca é escrita no compasso onde a frase começa.

Sem LLM: só contagem de notas fora da escala e regras de leitura.
"""
from __future__ import annotations

import metrica
import numpy as np

BLOCO = 16          # tempos (4 compassos 4/4)
MIN_BLOCOS = 4      # 16 compassos: ponte de 8 compassos se escreve com acidentes (como nas cifras)
PAUSA_FRASE = 1.0   # pausa da melodia (tempos) que separa frases
JANELA_FRASE = 4.0  # começo de frase até 1 compasso da fronteira do bloco conta


# peso da tônica: a armadura é a do tom (Krumhansl-Kessler), não só a que tem menos acidentes.
# Sem isso, música mixolídia (Si♭ com o Lá♭ do Si♭7, Águas de Março) ganhava a armadura de Mi♭.
PESO_TONICA = 0.5


def _correlacao_tons(peso) -> np.ndarray:
    """Correlação do histograma com cada armadura (-6..5): melhor entre o maior e o relativo menor."""
    from tonalidade import _perfis
    if peso.sum() <= 0 or peso.std() == 0:
        return np.zeros(12)
    h = (peso - peso.mean()) / peso.std()
    corr = _perfis() @ h / 12   # 24 tons: 2t = maior de t, 2t+1 = menor de t
    saida = np.zeros(12)
    for i, s in enumerate(range(-6, 6)):
        t = (7 * s) % 12
        saida[i] = max(corr[2 * t], corr[2 * ((t + 9) % 12) + 1])
    return saida


def custo_do_histograma(peso) -> np.ndarray:
    """Para cada armadura (-6..5): peso das notas com acidente + distância do tom mais provável."""
    peso = np.asarray(peso, dtype=float)
    custo = np.zeros(12)
    for i, s in enumerate(range(-6, 6)):
        t = (7 * s) % 12
        escala = {(t + k) % 12 for k in (0, 2, 4, 5, 7, 9, 11)}
        custo[i] = sum(peso[pc] for pc in range(12) if pc not in escala) + 0.002 * abs(s) * peso.sum()
    corr = _correlacao_tons(peso)
    return custo + PESO_TONICA * (corr.max() - corr) * peso.sum()


def custo_por_armadura(eventos) -> np.ndarray:
    """Para cada armadura (-6..5), custo de escrever esses eventos nela. eventos: (dur, [midis])."""
    peso = np.zeros(12)
    for d, ps in eventos:
        for p in ps:
            peso[p % 12] += d
    return custo_do_histograma(peso)


def inicios_de_frase(melodia_off) -> list[float]:
    """Ataques da melodia que vêm depois de pausa >= PAUSA_FRASE (e o primeiro)."""
    ev = sorted((o, o + d) for o, d, *_ in melodia_off)
    saida, fim_ant = [], None
    for o, f in ev:
        if fim_ant is None or o - fim_ant >= PAUSA_FRASE - 1e-6:
            saida.append(o)
        fim_ant = f if fim_ant is None else max(fim_ant, f)
    return saida


def armaduras_por_trecho(eventos_off, fim: float, frases=(), bloco: int = BLOCO,
                         min_blocos: int = MIN_BLOCOS, fator_troca: float = .5):
    """[(offset, sustenidos)] das mudanças. eventos_off: (offset, dur, [midis]) com offset >= 0."""
    nb = max(1, int(np.ceil(fim / bloco)))
    hist = np.zeros((nb, 12))
    peso = np.zeros(nb)
    for o, d, ps in eventos_off:
        b = min(nb - 1, int(o // bloco))
        for p in ps:
            hist[b, p % 12] += d
        peso[b] += d * len(ps)
    custos = np.array([custo_do_histograma(h) for h in hist])
    acum = np.vstack([np.zeros(12), np.cumsum(custos, axis=0)])
    troca = fator_troca * float(np.median(peso[peso > 0])) if (peso > 0).any() else 0.0
    frases = sorted(frases)

    def frase_perto(b):
        x = b * bloco
        perto = [f for f in frases if abs(f - x) <= JANELA_FRASE * metrica.TEMPOS / 4]
        return min(perto, key=lambda f: abs(f - x)) if perto else None

    def custo_troca(b):
        return troca * (1.0 if frase_perto(b) is not None else 2.0)

    if nb < 2 * min_blocos:  # curta demais pra modular
        return [(0.0, int(np.argmin(acum[nb])) - 6)]
    INF = float("inf")
    best = np.full((nb + 1, 12), INF)
    back = np.full((nb + 1, 12, 2), -1, dtype=int)  # (início do segmento, armadura anterior)
    for e in range(min_blocos, nb + 1):
        for s in range(0, e - min_blocos + 1):
            seg = acum[e] - acum[s]
            if s == 0:
                cand, prev = seg, np.full(12, -1)
            else:
                if e - s < min_blocos or s < min_blocos:
                    continue
                ant = best[s]
                if not np.isfinite(ant).any():
                    continue
                # anterior com armadura diferente: a melhor e a segunda melhor bastam
                ordem = np.argsort(ant)
                k1, k2 = int(ordem[0]), int(ordem[1])
                prev = np.where(np.arange(12) == k1, k2, k1)
                cand = ant[prev] + custo_troca(s) + seg
            melhora = cand < best[e]
            best[e] = np.where(melhora, cand, best[e])
            back[e, melhora, 0] = s
            back[e, melhora, 1] = prev[melhora]
    k = int(np.argmin(best[nb]))
    e = nb
    segmentos = []
    while e > 0:
        s, kp = back[e, k]
        segmentos.append((s, k))
        e, k = s, kp
    mudancas = []
    for s, k in reversed(segmentos):
        off = 0.0 if s == 0 else float(s * bloco)
        f = frase_perto(s) if s else None
        if f is not None:
            off = float(np.floor(f / metrica.TEMPOS) * metrica.TEMPOS)  # armadura no começo do compasso da frase
        mudancas.append((off, int(k) - 6))
    return mudancas
