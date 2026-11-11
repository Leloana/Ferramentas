"""Tocabilidade e leitura do arranjo, por regra (sem LLM e sem modelo): medir e corrigir.

O AMT-APC dá o arranjo; estes passos determinísticos deixam ele mais fácil de tocar e de ler.
Mesma entrada, mesma saída. Eventos do gerar.py: (offset_em_tempos, duração, [midis], *resto).

Medidas (`medir`): ataques por tempo (média e pior compasso), notas juntas, síncopes que
atravessam o tempo, saltos da esquerda maiores que uma oitava em pouco tempo, mudanças de
posição da mão por minuto e trechos que a mão não alcança (modelo do `maos.py`).
"""
from __future__ import annotations

import math

EPS = 1e-6


def _ataques(ev):
    """{offset: [midis]} juntando eventos que atacam no mesmo instante."""
    a = {}
    for off, dur, ps, *_ in ev:
        if ps:
            a.setdefault(round(off, 6), []).extend(ps)
    return a


def sincopes(ev):
    """Ataques fora do tempo cuja nota atravessa o tempo seguinte (antecipação)."""
    n = 0
    for off, dur, ps, *_ in ev:
        if not ps:
            continue
        frac = off - math.floor(off + EPS)
        if frac > EPS and off + dur > math.floor(off + EPS) + 1 + EPS:
            n += 1
    return n


def saltos(ev, max_tempos=1.0, limite=12):
    """Ataques seguidos cujo baixo salta mais que `limite` semitons em menos de `max_tempos`."""
    a = sorted(_ataques(ev).items())
    n = 0
    for (o1, p1), (o2, p2) in zip(a, a[1:]):
        if o2 - o1 < max_tempos - EPS and abs(min(p2) - min(p1)) > limite:
            n += 1
    return n


def densidade(ev, compasso=4.0):
    """(ataques por tempo na média, no compasso mais cheio)."""
    a = _ataques(ev)
    if not a:
        return 0.0, 0.0
    por_compasso = {}
    for o in a:
        k = int(o // compasso + EPS)
        por_compasso[k] = por_compasso.get(k, 0) + 1
    fim = max(o for o in a) - min(o for o in a) + 1
    return len(a) / fim, max(por_compasso.values()) / compasso


def medir(md, me, bpm, nivel):
    from maos import tornar_tocavel
    _, _, _, _, rel = tornar_tocavel(md, me, nivel, bpm, corrigir=False)
    fim = max([o + d for o, d, *_ in md + me] or [0])
    minutos = max(fim * 60 / bpm / 60, 1e-6)
    r = {}
    for lado, ev in (("direita", md), ("esquerda", me)):
        med, pior = densidade(ev)
        r[lado] = dict(ataques_por_tempo=round(med, 2), pior_compasso=round(pior, 2),
                       notas_juntas=max([len(set(p)) for p in _ataques(ev).values()] or [0]),
                       sincopes=sincopes(ev), saltos=saltos(ev),
                       mudancas_por_min=round(rel["mudancas_de_posicao"][lado] / minutos, 1))
    r["dificeis"] = rel["resumo"]["restantes"]
    return r


# ------------------------------------------------------------------ correções

def desfazer_sincopes(ev, min_dur=0.5, max_salto=7, nivel="facil", bpm=None):
    """Antecipação vira ataque no tempo: nota que começa fora do tempo e atravessa o seguinte passa
    a começar nele (mais curta), e a nota anterior que acabava ali segura até o novo ataque.
    Não mexe quando já há outro ataque nesse intervalo, quando a nota ficaria curta demais ou
    quando ela salta mais que `max_salto` semitons da próxima e o tempo que sobra não dá pra mão
    chegar (modelo do `maos.PERFIL`: base + distância/velocidade do nível; sem bpm, não move)."""
    from maos import PERFIL
    perfil = PERFIL[nivel]
    ev = sorted(ev, key=lambda e: e[0])
    inicios = [e[0] for e in ev]
    saida, mudou = [], 0
    for i, e in enumerate(ev):
        off, dur, ps, *r = e
        base = math.floor(off + EPS)
        novo = base + 1.0
        frac = off - base
        livre = not any(off + EPS < o <= novo + EPS for j, o in enumerate(inicios) if j != i)
        perto = True
        prox = next((x for x in ev[i + 1:] if x[2]), None)
        if ps and prox is not None:
            salto = max(abs(max(prox[2]) - max(ps)), abs(min(prox[2]) - min(ps)))
            if salto > max_salto:
                precisa = perfil["base"] + salto / perfil["vel"]
                perto = bpm is not None and (prox[0] - novo) * 60 / bpm >= precisa - EPS
        if ps and frac > EPS and off + dur > novo + EPS and off + dur - novo >= min_dur - EPS and livre and perto:
            if saida and abs(saida[-1][0] + saida[-1][1] - off) < EPS:
                a = saida[-1]
                saida[-1] = (a[0], novo - a[0], *a[2:])
            saida.append((novo, off + dur - novo, ps, *r))
            mudou += 1
        else:
            saida.append(e)
    return saida, mudou


def _centro(ps):
    return (min(ps) + max(ps)) / 2


def oitavas_da_esquerda(me, md, faixa=(28, 64), mudar=3.0, folga=7):
    """Programação dinâmica na oitava de cada ataque da esquerda (−12, 0, +12): a mão anda menos.

    Custo: deslocamento do centro além de `folga` semitons, mais caro quanto menos tempo houver
    (ataque colado), + `mudar` por ataque fora da oitava do arranjo. Proibido: sair da faixa ou
    encostar na nota mais grave da direita que soa junto."""
    ev = sorted(me, key=lambda e: e[0])
    if len(ev) < 2:
        return ev, 0
    opcoes = (0, -12, 12)

    def pode(i, k):
        off, dur, ps = ev[i][0], ev[i][1], ev[i][2]
        if not ps:
            return k == 0
        q = [p + k for p in ps]
        if min(q) < faixa[0] or max(q) > faixa[1]:
            return False
        topo = [min(p2) for o2, d2, p2, *_ in md if p2 and o2 < off + dur - EPS and off < o2 + d2 - EPS]
        return not topo or max(q) < min(topo)

    INF = float("inf")
    custo = [{k: (0.0 if k == 0 else mudar) if pode(0, k) else INF for k in opcoes}]
    volta = [{}]
    for i in range(1, len(ev)):
        ioi = max(ev[i][0] - ev[i - 1][0], .25)
        c, v = {}, {}
        for k in opcoes:
            if not pode(i, k):
                c[k] = INF
                continue
            melhor, arg = INF, 0
            for kp in opcoes:
                if custo[-1][kp] == INF:
                    continue
                if ev[i][2] and ev[i - 1][2]:
                    d = abs(_centro([p + k for p in ev[i][2]]) - _centro([p + kp for p in ev[i - 1][2]]))
                else:
                    d = 0
                t = custo[-1][kp] + max(0.0, d - folga) / ioi
                if t < melhor:
                    melhor, arg = t, kp
            c[k], v[k] = melhor + (0.0 if k == 0 else mudar), arg
        if all(x == INF for x in c.values()):   # nada cabe: fica como está daqui pra frente
            c = {k: (0.0 if k == 0 else INF) for k in opcoes}
            v = {0: min(custo[-1], key=custo[-1].get)}
        custo.append(c)
        volta.append(v)
    k = min(custo[-1], key=custo[-1].get)
    escolha = [0] * len(ev)
    for i in range(len(ev) - 1, -1, -1):
        escolha[i] = k
        k = volta[i].get(k, 0) if i else 0
    saida = [(off, dur, sorted(p + s for p in ps), *r) for (off, dur, ps, *r), s in zip(ev, escolha)]
    return saida, sum(1 for s in escolha if s)


_DIATONICO = (0, 0, 1, 2, 2, 3, 3, 4, 4, 5, 6, 6)   # classe de altura -> grau (grafia mais comum)


def suplementares_sol(m):
    """Linhas suplementares de uma nota MIDI na clave de sol (Dó4 = 1 embaixo, Lá5 = 1 em cima)."""
    d = _DIATONICO[m % 12] + 7 * (m // 12 - 1) + 1     # Dó4 = 29, como o diatonicNoteNum do music21
    if d >= 41:
        return (d - 39) // 2
    if d <= 29:
        return (31 - d) // 2
    return 0


def oitava_por_frase(md, me, opcoes=(0, -12, 12), pausa=1.0, mudar=3.0, salto=12, max_tempos=16.0, abrir_8va=6.0):
    """Fácil: cada frase da direita (separada por pausa >= `pausa` tempos) na oitava com menos linhas
    suplementares (em cima e embaixo pesam igual); sem pausa, a frase fecha na barra depois de
    `max_tempos` (o AMT-APC quase não tem pausa). Dentro da frase o desenho da melodia não muda.
    Só muda a frase de oitava se ficar melhor que escrevê-la sob 8va (`abrir_8va`, o mesmo custo do
    gerar.OITAVA_ABRIR).
    Programação dinâmica nas frases: + `mudar` por frase fora da oitava original, + o que passar de
    `salto` semitons entre o fim de uma frase e o começo da seguinte. Proibido encostar na esquerda."""
    ev = sorted(md, key=lambda e: e[0])
    if not ev:
        return md, 0
    frases, atual, fim = [], [], None
    for e in ev:
        longa = atual and e[0] - atual[0][0] >= max_tempos - EPS and abs(e[0] / 4 - round(e[0] / 4)) < EPS
        if atual and (e[0] - fim >= pausa - EPS or longa):
            frases.append(atual)
            atual = []
        atual.append(e)
        fim = e[0] + e[1] if fim is None else max(fim, e[0] + e[1])
    frases.append(atual)

    def cruza(fr, k):
        for off, dur, ps, *_ in fr:
            if ps and any(p2 and o2 < off + dur - EPS and off < o2 + d2 - EPS and max(p2) >= min(ps) + k
                          for o2, d2, p2, *_ in me):
                return True
        return False

    def leitura(fr, k):
        """Linhas suplementares da frase na oitava k, ou a frase sob 8va se ficar melhor (a 8va do
        gerar resolve agudo; nota que cairia embaixo da pauta dentro dela é proibida)."""
        alturas = [p + k for _, _, ps, *_ in fr for p in ps]
        normal = sum(suplementares_sol(p) for p in alturas)
        em8 = abrir_8va + sum(suplementares_sol(p - 12) * (100 if p - 12 < 62 else 1) for p in alturas)
        return min(normal, em8)

    INF = float("inf")
    custo = [{k: (INF if cruza(fr, k) else leitura(fr, k) + (mudar if k else 0)) for k in opcoes} for fr in frases]
    melhor, volta = [dict(custo[0])], [{}]
    for i in range(1, len(frases)):
        ult = max(frases[i - 1][-1][2]) if frases[i - 1][-1][2] else None
        pri = max(frases[i][0][2]) if frases[i][0][2] else None
        c, v = {}, {}
        for k in opcoes:
            if custo[i][k] == INF:
                c[k] = INF
                continue
            def t(kp):
                pulo = abs((pri + k) - (ult + kp)) if ult is not None and pri is not None else 0
                return melhor[-1][kp] + max(0, pulo - salto)
            kp = min(opcoes, key=t)
            c[k], v[k] = t(kp) + custo[i][k], kp
        melhor.append(c)
        volta.append(v)
    k = min(opcoes, key=lambda x: melhor[-1][x])
    escolha = [0] * len(frases)
    for i in range(len(frases) - 1, -1, -1):
        escolha[i] = k
        k = volta[i].get(k, 0) if i else 0
    saida = [(off, dur, [p + k for p in ps], *r) for fr, k in zip(frases, escolha) for off, dur, ps, *r in fr]
    return saida, sum(1 for k in escolha if k)


def custo_leitura(md, abrir=6.0, peso_embaixo=100.0, respiro=2.0):
    """Custo de ler a direita depois da 8va do gerar (`_oitava_acima`), na mesma programação dinâmica:
    linhas suplementares + `abrir` por linha 8va (metade depois de pausa longa), nota embaixo da
    pauta dentro da 8va × `peso_embaixo`. Serve pra comparar arranjos antes de escrever."""
    ev = sorted((e for e in md if e[2]), key=lambda e: e[0])
    if not ev:
        return 0.0

    def c(ps, s):
        tot = 0.0
        for p in ps:
            q = p - 12 * s
            tot += suplementares_sol(q) * (peso_embaixo if s and q < 62 else 1.0)
        return tot
    melhor = [c(ev[0][2], 0), c(ev[0][2], 1) + abrir]
    for a_, b_ in zip(ev, ev[1:]):
        abre = abrir / 2 if b_[0] - (a_[0] + a_[1]) > respiro + EPS else abrir
        melhor = [min(melhor) + c(b_[2], 0),                       # fechar a 8va é de graça
                  min(melhor[0] + abre, melhor[1]) + c(b_[2], 1)]
    return min(melhor)


def graves_pra_esquerda(md, me, abertura=12, max_notas=4, limite=62):
    """Nota da direita abaixo de `limite` (Ré4) vai pra esquerda quando a esquerda pode pegar: livre
    no instante, ou atacando junto com a mesma duração e o acorde junto cabe na mão (`abertura`
    semitons, até `max_notas`). A nota de cima da direita (a melodia) nunca sai."""
    me = sorted(me, key=lambda e: e[0])
    saida_md, movidas = [], 0
    for off, dur, ps, *r in sorted(md, key=lambda e: e[0]):
        ps = sorted(ps)
        graves = [p for p in ps[:-1] if p < limite]
        if not graves:
            saida_md.append((off, dur, ps, *r))
            continue
        juntos = [i for i, (o2, d2, p2, *_) in enumerate(me) if p2 and o2 < off + dur - EPS and off < o2 + d2 - EPS]
        alvo = None
        if not juntos:
            alvo = "livre"
        elif len(juntos) == 1:
            o2, d2, p2 = me[juntos[0]][:3]
            novo = sorted(set(p2) | set(graves))
            if abs(o2 - off) < EPS and abs(d2 - dur) < EPS and novo[-1] - novo[0] <= abertura \
                    and len(novo) <= max_notas and max(novo) < ps[-1]:
                alvo = juntos[0]
        if alvo is None:
            saida_md.append((off, dur, ps, *r))
            continue
        if alvo == "livre":
            if max(graves) - min(graves) > abertura:
                saida_md.append((off, dur, ps, *r))
                continue
            me.append((off, dur, graves))
            me.sort(key=lambda e: e[0])
        else:
            o2, d2, p2, *r2 = me[alvo]
            me[alvo] = (o2, d2, sorted(set(p2) | set(graves)), *r2)
        saida_md.append((off, dur, [p for p in ps if p not in graves], *r))
        movidas += len(graves)
    return saida_md, me, movidas


def ajustar(md, me, nivel, bpm):
    """Passos de tocabilidade por nível. Devolve (md, me, registro)."""
    from maos import PERFIL
    reg = {}
    if nivel == "facil":
        novo, n = oitava_por_frase(md, me)
        if n and custo_leitura(novo) < custo_leitura(md):   # só se ler ficar mais fácil depois da 8va
            md = novo
        reg["frases_em_outra_oitava"] = n if novo is md else 0
        md, reg["sincopes_direita"] = desfazer_sincopes(md, nivel=nivel, bpm=bpm)
    md, me, reg["graves_pra_esquerda"] = graves_pra_esquerda(md, me, abertura=PERFIL[nivel]["abertura"])
    if nivel in ("facil", "medio"):
        me, reg["sincopes_esquerda"] = desfazer_sincopes(me, nivel=nivel, bpm=bpm)
    if nivel in ("facil", "medio"):   # no difícil a esquerda é arpejo nota a nota: oitava por nota desmancharia o desenho
        from niveis import GRAVE_MINIMO
        me, reg["oitavas_esquerda"] = oitavas_da_esquerda(me, md, (36, 64) if nivel == "facil" else (GRAVE_MINIMO, 64))
    return md, me, reg
