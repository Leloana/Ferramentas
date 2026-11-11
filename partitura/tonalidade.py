"""Nota fora do tom no arranjo da IA (AMT-APC), corrigida por regras de harmonia. Sem LLM.

Medição (2026-11-11): 7,8% das notas da voz de cima do AMT-APC caem fora da escala e do acorde,
quase todas firmes (não são deslizes curtos como na voz). Parte disso é música de verdade
(cromatismo da bossa, 7ª/9ª/13ª): só o erro provável muda.

1. Tom por trecho: perfis de Krumhansl–Kessler sobre as notas (peso = duração) em janelas de
   4 tempos, Viterbi nos 24 tons com custo pra modular (sem trocar de tom a cada compasso).
2. Vocabulário da música: classe de altura que aparece muito e em muitos compassos (a b7 de um
   blues, um empréstimo modal, o cromatismo recorrente) entra na escala daquela música.
3. Por função (fica): nota do acorde do momento (com 7ª e extensões detectadas), bordadura,
   passagem por grau conjunto em tempo fraco, apojatura que resolve por grau conjunto, sensível
   da fundamental do acorde seguinte.
4. Erro provável (muda): fora da escala+vocabulário+acorde e sem função, ou nota que não é do
   acorde um semitom acima de nota do acorde que soa junto na outra mão (a 7ª maior fica). Vai pra nota permitida mais perto (até 2 semitons),
   preferindo nota do acorde e a direção da nota seguinte; nota curta e fraca num acorde sai.
Eventos do gerar.py: (offset_em_tempos, duração, [midis], *resto).
"""
from __future__ import annotations

import numpy as np

EPS = 1e-6
# Krumhansl & Kessler (1982)
_MAIOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
ESCALA_MAIOR = (0, 2, 4, 5, 7, 9, 11)
ESCALA_MENOR = (0, 2, 3, 5, 7, 8, 10, 11)   # natural + harmônica (sensível)


def _perfis():
    p = []
    for t in range(12):
        p.append(np.roll(_MAIOR, t))
        p.append(np.roll(_MENOR, t))
    p = np.array(p)
    return (p - p.mean(axis=1, keepdims=True)) / p.std(axis=1, keepdims=True)


def tons_por_trecho(eventos, janela=4.0, troca=2.5):
    """{índice da janela: (tônica, 'maior'|'menor')} por Viterbi sobre a correlação com os perfis."""
    if not eventos:
        return {}, janela
    fim = max(o + d for o, d, *_ in eventos)
    n = int(fim // janela) + 1
    hist = np.zeros((n, 12))
    for o, d, ps, *_ in eventos:
        for p in ps:
            k = int(o // janela)
            if 0 <= k < n:
                hist[k, p % 12] += min(d, janela)
    # suaviza com as janelas vizinhas (tom é coisa de frase, não de compasso)
    suave = hist.copy()
    suave[1:] += .5 * hist[:-1]
    suave[:-1] += .5 * hist[1:]
    perfis = _perfis()
    score = np.zeros((n, 24))
    for k in range(n):
        h = suave[k]
        if h.sum() > 0:
            z = (h - h.mean()) / (h.std() + 1e-9)
            score[k] = perfis @ z / 12
    custo = np.zeros(24)
    trilha = np.zeros((n, 24), dtype=int)
    for k in range(n):
        if k:
            cand = custo[None, :] - troca * (1 - np.eye(24))   # [novo, anterior]
            trilha[k] = cand.argmax(axis=1)
            custo = cand.max(axis=1)
        custo = custo + score[k]
    s = int(custo.argmax())
    caminho = [s]
    for k in range(n - 1, 0, -1):
        s = int(trilha[k, s])
        caminho.append(s)
    caminho.reverse()
    return {k: (c // 2, "maior" if c % 2 == 0 else "menor") for k, c in enumerate(caminho)}, janela


def escala(tom):
    t, modo = tom
    return {(t + i) % 12 for i in (ESCALA_MAIOR if modo == "maior" else ESCALA_MENOR)}


def vocabulario(eventos, tons, janela, minimo=.04, compassos_min=4):
    """Classes de altura fora da escala que a música usa de verdade (muito e em vários compassos)."""
    peso, onde, total = np.zeros(12), [set() for _ in range(12)], 0.0
    for o, d, ps, *_ in eventos:
        e = escala(tons.get(int(o // janela), (0, "maior")))
        for p in ps:
            total += d
            if p % 12 not in e:
                peso[p % 12] += d
                onde[p % 12].add(int(o // 4))
    return {pc for pc in range(12) if total and peso[pc] / total >= minimo and len(onde[pc]) >= compassos_min}


def _acorde(acs, tipos, t, janela=2):
    for j, r, ti, *_ in reversed(acs):
        if j <= t + EPS:
            if r is None or t >= j + janela:
                return None, set()
            return r, {(r + i) % 12 for i in tipos[ti][0]}
    return None, set()


def _proximo_acorde(acs, t):
    ant = None
    for j, r, ti, *_ in acs:
        if j > t + EPS and r is not None and (r, ti) != ant:
            return r
        if j <= t + EPS:
            ant = (r, ti)
    return None


def corrigir_tom(md, me, acs, tipos, passo_curto=.5):
    """Devolve (md, me, registro). Corrige as duas mãos do arranjo."""
    md = sorted(md, key=lambda e: e[0])
    me = sorted(me, key=lambda e: e[0])
    todos = md + me
    tons, jan = tons_por_trecho(todos)
    if not tons:
        return md, me, []
    voc = vocabulario(todos, tons, jan)
    registro = []

    def permitidas(t):
        raiz, ac = _acorde(acs, tipos, t)
        return escala(tons.get(int(t // jan), (0, "maior"))) | voc | ac, ac

    def soando(lado, t, d):
        return [p for o, du, ps, *_ in lado for p in ps if o < t + d - EPS and o + du > t + EPS]

    def corrigir_nota(p, t, d, viz_ant, viz_prox, outra, fraca):
        perm, ac = permitidas(t)
        # choque: nota que não é do acorde um semitom (ou nona menor) ACIMA de nota do acorde que soa
        # junto. A 7ª maior (Si sobre Dó no C7M) e a nota do próprio acorde não são choque
        choque = bool(ac) and p % 12 not in ac and any(
            p > q and (p - q) % 12 == 1 and q % 12 in ac for q in soando(outra, t, d))
        if p % 12 in perm and not choque:
            return p, None
        if p % 12 not in perm and not choque:
            # função melódica: fica
            if viz_ant is not None and viz_prox is not None:
                if viz_ant == viz_prox and abs(p - viz_ant) <= 2:
                    return p, None                                          # bordadura
                if 0 < abs(p - viz_ant) <= 2 and 0 < abs(viz_prox - p) <= 2 and \
                        (viz_prox - p) * (p - viz_ant) > 0 and d <= 1 + EPS and fraca:
                    return p, None                                          # passagem
            if viz_prox is not None and 0 < abs(viz_prox - p) <= 2 and viz_prox % 12 in perm and d <= 1 + EPS:
                return p, None                                              # apojatura que resolve
            prox = _proximo_acorde(acs, t)
            if prox is not None and (p + 1) % 12 == prox:
                return p, None                                              # sensível do próximo acorde
        # erro provável: nota permitida mais perto (prefere acorde e a direção da próxima nota)
        cands = [q for q in range(p - 2, p + 3) if q != p and q % 12 in perm
                 and not any(q > r and (q - r) % 12 == 1 for r in soando(outra, t, d))]
        if not cands:
            return p, None
        alvo = viz_prox if viz_prox is not None else p

        def chave(q):
            return (abs(q - p), q % 12 not in ac, abs(q - alvo))
        return min(cands, key=chave), ("choque" if choque else "fora do tom")

    def mao(lado, outra, nome):
        saida = []
        topo = [max(e[2]) if e[2] else None for e in lado]
        for i, ev in enumerate(lado):
            o, d, ps = ev[0], ev[1], list(ev[2])
            fraca = abs(o - round(o)) > EPS or int(round(o)) % 2 == 1
            novos = []
            for p in ps:
                eh_topo = p == topo[i]
                ant = topo[i - 1] if (eh_topo and i > 0) else None
                prox = topo[i + 1] if (eh_topo and i + 1 < len(lado)) else None
                q, motivo = corrigir_nota(p, o, d, ant, prox, outra, fraca)
                if motivo and not eh_topo and len(ps) > 1 and d < passo_curto - EPS and fraca:
                    registro.append(dict(mao=nome, ini=round(o, 3), antes=p, depois=None, motivo=motivo))
                    continue                                                # nota interna curta e fraca: sai
                if motivo:
                    registro.append(dict(mao=nome, ini=round(o, 3), antes=p, depois=q, motivo=motivo))
                novos.append(q)
            if novos:
                saida.append((o, d, sorted(set(novos)), *ev[3:]))
        return saida

    md2 = mao(md, me, "direita")
    me2 = mao(me, md2, "esquerda")
    return md2, me2, registro
