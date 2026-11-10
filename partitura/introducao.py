"""Introdução gerada: não existe na gravação; é criada a partir da própria música.

Sem LLM e sem sorteio: regras musicais. A mesma música, teor, nível e variação dão sempre
a mesma introdução; `variacao` troca de forma controlada a origem do motivo (começo do
refrão, 2º compasso dele, frase seguinte), o registro e o sentido do arpejo.

1. Material: o refrão (frase cuja letra mais se repete; sem letra, o desenho melódico que
   mais se repete; senão a primeira frase longa). Do começo dele sai um motivo de até 2
   compassos, com os acordes que tocam embaixo. A introdução lembra a música sem ser um
   trecho dela.
2. Teor (o que a pessoa escolhe) muda textura, registro, duração e dinâmica:
   calma, lenta, emotiva, animada, epica.
3. Nível muda a densidade: fácil = uma nota por mão, semínimas/mínimas, 4 compassos;
   médio = padrões simples, 4 compassos; difícil = arpejos e dobramentos, 8 compassos.
4. Último compasso: dominante do primeiro acorde da música, pra desembocar nela.

Saída em tempos a partir de 0: (direita, esquerda, cifras, info). Quem chama desloca pra
antes do primeiro compasso da música; a correção das mãos e os dedos valem pra ela também.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

TEORES = ("calma", "lenta", "emotiva", "animada", "epica")
NOME_TEOR = {"calma": "calma", "lenta": "lenta", "emotiva": "emotiva", "animada": "animada", "epica": "épica"}
COMPASSOS = {"facil": 4, "medio": 4, "dificil": 8}
GRADE = {"facil": 1.0, "medio": .5, "dificil": .25}
DINAMICA = {"calma": "p", "lenta": "pp", "emotiva": "mp", "animada": "mf", "epica": "f"}
# esticar o motivo (lenta = durações dobradas)
AUMENTO = {"calma": 1, "lenta": 2, "emotiva": 1, "animada": 1, "epica": 1}
# centro do registro da melodia da introdução
REGISTRO = {"calma": 69, "lenta": 67, "emotiva": 71, "animada": 76, "epica": 74}
PAUSA_FRASE = 1.0
EPS = 1e-6


# ------------------------------------------------------------------ refrão e motivo

def _norm(txt):
    txt = unicodedata.normalize("NFD", (txt or "").lower())
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", txt)


def frases(md_ev):
    """Melodia em frases separadas por pausa >= 1 tempo."""
    ev = sorted(md_ev, key=lambda e: e[0])
    saida, atual, fim = [], [], None
    for e in ev:
        if atual and e[0] - fim >= PAUSA_FRASE - EPS:
            saida.append(atual)
            atual = []
        atual.append(e)
        fim = e[0] + e[1] if fim is None else max(fim, e[0] + e[1])
    if atual:
        saida.append(atual)
    return saida


def achar_refrao(md_ev):
    """(frase do refrão, como achou)."""
    fr = [f for f in frases(md_ev) if len(f) >= 3]
    if not fr:
        return (sorted(md_ev, key=lambda e: e[0]), "melodia inteira")
    textos = [_norm("".join(str(e[3]) for e in f if len(e) > 3 and e[3])) for f in fr]
    cont = Counter(t for t in textos if len(t) >= 6)
    if cont:
        texto, n = max(cont.items(), key=lambda kv: (kv[1], len(kv[0])))
        if n >= 2:
            return fr[textos.index(texto)], f"letra que mais se repete ({n}x)"

    def desenho(f):
        ps = [e[2][-1] for e in f[:7]]
        return tuple(b - a for a, b in zip(ps, ps[1:]))
    desenhos = [desenho(f) for f in fr if len(f) >= 5]
    cont = Counter(desenhos)
    if cont:
        d, n = cont.most_common(1)[0]
        if n >= 2:
            return next(f for f in fr if len(f) >= 5 and desenho(f) == d), f"desenho melódico repetido ({n}x)"
    return max(fr[:4], key=lambda f: len(f)), "primeira frase longa"


def motivo(frase, max_tempos=8.0, ini=None):
    """[(offset relativo a ini, dur, nota mais aguda)] da frase, até max_tempos.
    ini: começo do compasso da frase (a anacruse fica no lugar)."""
    ini = frase[0][0] if ini is None else ini
    saida = []
    for o, d, ps, *_ in frase:
        rel = o - ini
        if rel >= max_tempos - EPS:
            break
        saida.append((rel, min(d, max_tempos - rel), max(ps)))
    return saida


def acordes_em(acs, ini, fim):
    """[(offset relativo, raiz, tipo)] dos acordes detectados em [ini, fim), sem repetição seguida."""
    saida, ant = [], None
    for j, r, t, *_ in acs:
        if r is None or j < ini - EPS or j >= fim - EPS:
            continue
        if (r, t) != ant:
            saida.append((j - ini, r, t))
        ant = (r, t)
    return saida


def primeiro_acorde(acs, a_partir=None):
    for j, r, t, *_ in acs:
        if r is not None and (a_partir is None or j >= a_partir - EPS):
            return r, t
    return None


# ------------------------------------------------------------------ texturas

def _quantizar(eventos, passo, fim):
    """Ataques e durações na grade do nível; sem sobreposição; corta no fim."""
    saida = []
    for o, d, ps in sorted(eventos, key=lambda e: e[0]):
        o2 = round(o / passo) * passo
        if saida and o2 < saida[-1][0] + saida[-1][1] - EPS:
            if o2 <= saida[-1][0] + EPS:
                continue
            ant = saida[-1]
            saida[-1] = (ant[0], o2 - ant[0], ant[2])
        d2 = max(passo, round(d / passo) * passo)
        d2 = min(d2, fim - o2)
        if d2 > EPS:
            saida.append((o2, d2, ps))
    return saida


def _no_registro(ps, centro):
    m = sum(ps) / len(ps)
    k = round((centro - m) / 12)
    return [p + 12 * k for p in ps]


def _pcs(r, t, tipos):
    return [(r + i) % 12 for i in tipos[t][0]]


def _nota_perto(pc, alvo):
    """Altura com classe pc mais perto de alvo."""
    return alvo + ((pc - alvo + 6) % 12) - 6


def _acorde_no_tempo(harmonia, t):
    atual = harmonia[0]
    for h in harmonia:
        if h[0] <= t + EPS:
            atual = h
    return atual


def mao_esquerda(harmonia, total, teor, nivel, tipos, variacao=0):
    """harmonia: [(offset, raiz, tipo)] cobrindo [0, total)."""
    ev = []
    for i, (o, r, t) in enumerate(harmonia):
        fim = harmonia[i + 1][0] if i + 1 < len(harmonia) else total
        dur = fim - o
        if dur <= EPS:
            continue
        pcs = _pcs(r, t, tipos)
        grave = 31 if teor == "epica" else 36
        raiz = grave + (r - grave % 12) % 12           # entre G1/C2 e uma oitava acima
        quinta = raiz + 7
        terca = raiz + (pcs[1] - r) % 12 + 12
        setima = raiz + (pcs[-1] - r) % 12 + 12 if len(pcs) == 4 else quinta + 12
        if nivel == "facil":
            pos = o
            while pos < fim - EPS:
                d = min(4.0 if teor in ("calma", "lenta", "epica") else 2.0, fim - pos)
                ev.append((pos, d, [raiz if raiz >= 41 else raiz + 12]))
                pos += d
            continue
        if teor in ("calma", "lenta"):
            vozes = [raiz, quinta] if nivel == "medio" else [raiz, quinta, terca]
            if nivel == "dificil" and teor == "calma":
                padrao = [raiz, quinta, raiz + 12, terca]
                passo = 1.0
                k, pos = 0, o
                while pos < fim - EPS:
                    ev.append((pos, min(passo, fim - pos), [padrao[k % 4]]))
                    pos += passo
                    k += 1
            else:
                pos = o
                while pos < fim - EPS:
                    d = min(4.0, fim - pos)
                    ev.append((pos, d, vozes))
                    pos += d
        elif teor == "emotiva":
            padrao = [raiz, quinta, terca, quinta] if nivel == "medio" else [raiz, quinta, raiz + 12, terca, raiz + 12, quinta]
            if variacao % 2:  # arpejo subindo e descendo no outro sentido (o baixo continua no tempo 1)
                padrao = [padrao[0]] + padrao[:0:-1]
            passo = 1.0 if nivel == "medio" else .5
            k, pos = 0, o
            while pos < fim - EPS:
                ev.append((pos, min(passo, fim - pos), [padrao[k % len(padrao)]]))
                pos += passo
                k += 1
        elif teor == "animada":
            acorde = sorted({terca, setima})
            passo = 1.0 if nivel == "medio" else .5
            k, pos = 0, o
            while pos < fim - EPS:
                if k % 2 == 0:
                    alterna = nivel == "dificil" and (k // 2) % 2 == 1   # baixo alternado: fundamental, quinta
                    baixo = (quinta - 12 if quinta - 12 >= 31 else quinta) if alterna else raiz
                    ev.append((pos, min(passo, fim - pos), [baixo]))
                else:
                    ev.append((pos, min(passo, fim - pos), acorde))
                pos += passo
                k += 1
        else:  # epica
            pos = o
            if nivel == "medio":
                while pos < fim - EPS:
                    d = min(2.0, fim - pos)
                    ev.append((pos, d, [raiz, raiz + 12]))
                    pos += d
            else:
                ev.append((pos, min(1.0, dur), [raiz, raiz + 12]))
                pos += 1.0
                while pos < fim - EPS:
                    ev.append((pos, min(1.0, fim - pos), sorted({raiz + 12, quinta + 12 if quinta + 12 < 60 else quinta, terca})))
                    pos += 1.0
    return ev


def mao_direita(notas, harmonia, teor, nivel, tipos):
    """Motivo já no tempo da introdução -> direita no teor/nível (dobramentos)."""
    ev = []
    for o, d, p in notas:
        _, r, t = _acorde_no_tempo(harmonia, o)
        pcs = _pcs(r, t, tipos)
        forte = abs(o - round(o)) < EPS and round(o) % 2 == 0
        ps = [p]
        if nivel == "dificil":
            if teor == "epica":
                ps = [p - 12, p]
                if forte:
                    abaixo = [q for q in (_nota_perto(pc, p - 5) for pc in pcs) if p - 12 < q < p]
                    ps = sorted(set(ps + abaixo[:1]))
            elif d >= 1 - EPS or forte:
                abaixo = [q for q in (_nota_perto(pc, p - 4) for pc in pcs) if p - 9 <= q < p - 2]
                ps = sorted(set([p] + abaixo[:1]))
        elif nivel == "medio" and teor in ("epica", "animada") and forte:
            abaixo = [q for q in (_nota_perto(pc, p - 4) for pc in pcs) if p - 9 <= q < p - 2]
            ps = sorted(set([p] + abaixo[:1]))
        ev.append((o, d, ps))
    return ev


# ------------------------------------------------------------------ introdução

def gerar_introducao(md_ev, acs, tipos, nivel, teor, inicio_musica=None, semente="", variacao=0):
    """(direita, esquerda, cifras, info) com offsets em [0, compassos*4)."""
    if teor not in TEORES:
        raise ValueError(f"teor inválido: {teor} (use {', '.join(TEORES)})")
    total = 4.0 * COMPASSOS[nivel]
    corpo = total - 4.0
    frase, como = achar_refrao(md_ev)
    # variação controlada: de onde vem o motivo, registro e ordem do arpejo
    fonte, reg = variacao % 3, [0, 12, -12][(variacao // 3) % 3]
    if fonte == 2:
        todas = frases(md_ev)
        seg = [f for f in todas if f[0][0] > frase[-1][0] and len(f) >= 3]
        if seg:
            frase, como = seg[0], como + ", frase seguinte"
    aum = AUMENTO[teor]
    janela = min(8.0, corpo / aum)
    janela = max(4.0, 4.0 * int(janela // 4))
    ini_frase = frase[0][0]
    compasso_frase = 4.0 * (ini_frase // 4)
    if fonte == 1 and frase[-1][0] >= compasso_frase + 4 + janela / 2:
        compasso_frase += 4.0
        como += ", 2º compasso"
    mot = motivo(frase, janela, compasso_frase)
    base_harm = acordes_em(acs, compasso_frase, compasso_frase + janela)
    if not base_harm:  # janela sem acorde detectado: o que estava soando antes
        ant = [(j, r, t) for j, r, t, *_ in acs if r is not None and j < compasso_frase]
        if ant:
            base_harm = [(0.0, ant[-1][1], ant[-1][2])]
    if base_harm:
        base_harm = [(max(0.0, o), r, t) for o, r, t in base_harm]
        if base_harm[0][0] > EPS:
            base_harm = [(0.0, base_harm[0][1], base_harm[0][2])] + base_harm[1:]
    entrada = primeiro_acorde(acs, inicio_musica) or (base_harm[0][1:] if base_harm else (0, "maj"))
    if not base_harm:
        base_harm = [(0.0, entrada[0], entrada[1])]
    # variação: o motivo pode começar uma oitava acima/abaixo e trocar a ordem das repetições
    centro = REGISTRO[teor] + reg
    alturas = _no_registro([p for _, _, p in mot], centro) if mot else []
    mot = [(o, d, p) for (o, d, _), p in zip(mot, alturas)]
    # corpo: enunciados do motivo (esticado) até encher; o 2º desce/sobe uma oitava no épico/animado
    notas, harmonia = [], []
    tam = janela * aum
    k, pos = 0, 0.0
    while pos < corpo - EPS:
        sobe = 12 if (k % 2 == 1 and teor in ("epica", "animada") and nivel == "dificil") else 0
        for o, d, p in mot:
            oo = pos + o * aum
            if oo < corpo - EPS:
                notas.append((oo, min(d * aum, corpo - oo), p + sobe))
        for o, r, t in base_harm:
            oo = pos + o * aum
            if oo < corpo - EPS:
                harmonia.append((oo, r, t))
        pos += tam
        k += 1
    # cadência: dominante do primeiro acorde da música
    r0 = entrada[0]
    dom = ((r0 + 7) % 12, "7")
    ultima = notas[-1][2] if notas else centro
    if teor == "emotiva" and nivel != "facil":
        sub = ((r0 + 5) % 12, "maj" if entrada[1] in ("maj", "7", "maj7", "6") else "m")
        harmonia += [(corpo, sub[0], sub[1]), (corpo + 2, dom[0], dom[1])]
        quarta = _nota_perto((dom[0] + 5) % 12, ultima)
        terca = _nota_perto((dom[0] + 4) % 12, quarta - 1)
        terca_sub = (sub[0] + tipos[sub[1]][0][1]) % 12
        notas += [(corpo, 2.0, _nota_perto(terca_sub, ultima)), (corpo + 2, 1.0, quarta), (corpo + 3, 1.0, terca)]
    else:
        harmonia.append((corpo, dom[0], dom[1]))
        alvo = _nota_perto((dom[0] + 7) % 12, ultima)   # 5ª da dominante: pede resolução
        if teor == "animada":
            notas += [(corpo + i, 1.0, alvo if i % 2 == 0 else _nota_perto((dom[0] + 4) % 12, alvo)) for i in range(4)]
        elif teor == "epica" and nivel != "facil":
            notas += [(corpo, 2.0, alvo), (corpo + 2, 2.0, _nota_perto((dom[0] + 4) % 12, alvo + 2))]
        else:
            notas.append((corpo, 4.0, alvo))
    harmonia = sorted({o: (o, r, t) for o, r, t in harmonia}.values())
    passo = GRADE[nivel]
    if nivel == "facil":
        passo = 1.0
    notas_q = _quantizar(notas, passo, total)
    direita = mao_direita(notas_q, harmonia, teor, nivel, tipos)
    esquerda = _quantizar(mao_esquerda(harmonia, total, teor, nivel, tipos, variacao), passo, total)
    cifras, ant = [], None
    for o, r, t in harmonia:
        if (r, t) != ant:
            cifras.append((o, r, t))
        ant = (r, t)
    info = dict(teor=teor, nivel=nivel, musica=semente, compassos=COMPASSOS[nivel], variacao=variacao,
                refrao=como, refrao_inicio=round(ini_frase, 3), motivo_tempos=janela,
                entrada=dict(raiz=r0, tipo=entrada[1]), dinamica=DINAMICA[teor])
    return [(o, d, ps, None) for o, d, ps in direita], esquerda, cifras, info
