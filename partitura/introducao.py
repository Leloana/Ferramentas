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
                if teor == "epica":   # exceção do fácil: oitava grave (mesma nota, fácil de ler) pra pesar
                    ev.append((pos, d, [raiz, raiz + 12]))
                else:
                    ev.append((pos, d, [raiz if raiz >= 41 else raiz + 12]))
                pos += d
            continue
        if teor in ("calma", "lenta"):
            # só notas longas (mínima ou mais): acorde aberto sustentado
            vozes = [raiz, quinta] if nivel == "medio" else [raiz, quinta, terca]
            pos = o
            while pos < fim - EPS:
                d = min(4.0, fim - pos)
                ev.append((pos, d, vozes))
                pos += d
        elif teor == "emotiva":
            # semínimas nos dois níveis (em colcheia ficava rápido e parecido com a animada);
            # no difícil o arpejo abre até a 10ª
            padrao = [raiz, quinta, terca, quinta] if nivel == "medio" else [raiz, quinta, terca, quinta + 12]
            if variacao % 2:  # arpejo no outro sentido (o baixo continua no tempo 1)
                padrao = [padrao[0]] + padrao[:0:-1]
            passo = 1.0
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
        else:  # epica: pesada, oitavas graves
            pos = o
            if nivel == "medio":   # oitava com a quinta no meio, em mínimas
                while pos < fim - EPS:
                    d = min(2.0, fim - pos)
                    ev.append((pos, d, [raiz, quinta, raiz + 12]))
                    pos += d
            else:                  # oitava no tempo 1 e acordes repetidos em colcheia (ostinato)
                ev.append((pos, min(1.0, dur), [raiz, raiz + 12]))
                pos += 1.0
                topo = sorted({raiz + 12, quinta + 12 if quinta + 12 < 60 else quinta, terca})
                while pos < fim - EPS:
                    ev.append((pos, min(.5, fim - pos), topo))
                    pos += .5
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


def _saltitar(notas, ate):
    """Animada: notas destacadas (metade da duração) e antecipação de colcheia no tempo 3."""
    saida = []
    for i, (o, d, p) in enumerate(notas):
        if o >= ate - EPS:
            saida.append((o, d, p))
            continue
        fim_ant = saida[-1][0] + saida[-1][1] if saida else -1
        if abs(o % 4 - 2) < EPS and fim_ant <= o - .5 + EPS:
            o, d = o - .5, d + .5            # antecipa o tempo 3
        if d >= 1 - EPS:
            d = d / 2                         # destacada
        saida.append((o, d, p))
    return saida


# ------------------------------------------------------------------ introdução

def gerar_introducao(md_ev, acs, tipos, nivel, teor, inicio_musica=None, semente="", variacao=0):
    """(direita, esquerda, cifras, info) com offsets em [0, compassos*4)."""
    if teor not in TEORES:
        raise ValueError(f"teor inválido: {teor} (use {', '.join(TEORES)})")
    total = 4.0 * COMPASSOS[nivel]
    # épica: antes da cadência, compassos de tensão (bVI -> bVII, a progressão "heroica")
    tensao = (4.0 if total <= 16 else 8.0) if teor == "epica" else 0.0
    corpo = total - 4.0 - tensao
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
    if tensao:
        # sobe por bVI e bVII (emprestados) com a melodia subindo por notas dos acordes,
        # a partir do registro do motivo (não da repetição uma oitava acima)
        while ultima > centro + 5:
            ultima -= 12
        passo_t = 1.0 if nivel != "facil" else 2.0
        for i, (rr, tt) in enumerate((((r0 + 8) % 12, "maj"), ((r0 + 10) % 12, "maj"))):
            o_seg = corpo + i * tensao / 2
            harmonia.append((o_seg, rr, tt))
            pcs_t = _pcs(rr, tt, tipos)
            pos_t = o_seg
            while pos_t < o_seg + tensao / 2 - EPS:
                acima = [q for q in (_nota_perto(pc, ultima + 3) for pc in pcs_t) if q > ultima]
                prox = min(acima) if acima else ultima + 2
                if prox > centro + 12:   # chegou no topo: fica em volta dele (nota do acorde mais perto)
                    prox = min((_nota_perto(pc, centro + 10) for pc in pcs_t), key=lambda q: abs(q - (centro + 10)))
                ultima = prox
                notas.append((pos_t, passo_t, ultima))
                pos_t += passo_t
        corpo = corpo + tensao   # a cadência vem depois da tensão
    if teor == "emotiva" and nivel != "facil":
        maior = entrada[1] in ("maj", "7", "maj7", "6")
        # difícil: iv menor emprestado (mais melancólico); médio: IV
        sub = ((r0 + 5) % 12, "m" if (nivel == "dificil" or not maior) else "maj")
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
        elif teor == "epica":
            # dominante suspensa (4ª) que só resolve na 3ª no meio do compasso
            quarta = _nota_perto((dom[0] + 5) % 12, ultima)
            notas += [(corpo, 2.0, quarta), (corpo + 2, 2.0, _nota_perto((dom[0] + 4) % 12, quarta - 1))]
        else:
            notas.append((corpo, 4.0, alvo))
    harmonia = sorted({o: (o, r, t) for o, r, t in harmonia}.values())
    passo = GRADE[nivel]
    if nivel == "facil":
        passo = 1.0
    notas_q = _quantizar(notas, passo, total)
    if teor == "animada" and nivel == "dificil":
        notas_q = _saltitar(notas_q, corpo)
    direita = mao_direita(notas_q, harmonia, teor, nivel, tipos)
    esquerda = _quantizar(mao_esquerda(harmonia, total, teor, nivel, tipos, variacao), passo, total)
    cifras, ant = [], None
    for o, r, t in harmonia:
        if (r, t) != ant:
            cifras.append((o, r, t))
        ant = (r, t)
    info = dict(teor=teor, nivel=nivel, musica=semente, compassos=COMPASSOS[nivel], variacao=variacao,
                refrao=como, refrao_inicio=round(ini_frase, 3), motivo_tempos=janela,
                entrada=dict(raiz=r0, tipo=entrada[1]), dinamica=DINAMICA[teor],
                dinamicas=([(0.0, "mp"), (corpo - tensao, "f"), (corpo, "ff")] if tensao
                           else [(0.0, DINAMICA[teor])]),
                pedal=_pedal_por_acorde(harmonia, total) if teor in COM_PEDAL else [])
    return [(o, d, ps, None) for o, d, ps in direita], esquerda, cifras, info


# ------------------------------------------------------------------ final gerado

COMPASSOS_FINAL = {"facil": 2, "medio": 2, "dificil": 4}
DINAMICAS_FINAL = {"calma": ("p", "pp"), "lenta": ("p", "pp"), "emotiva": ("mp", "p"),
                   "animada": ("mf", "f"), "epica": ("f", "ff")}
COM_PEDAL = ("calma", "lenta", "emotiva")
COM_FERMATA = ("calma", "lenta", "emotiva", "epica")
COM_RIT = ("calma", "lenta", "emotiva")


def _cadencia(teor, r0, maior):
    """Acordes do compasso antes do acorde final: [(offset no compasso, raiz, tipo)]."""
    iv = ((r0 + 5) % 12, "m")
    IV = ((r0 + 5) % 12, "maj" if maior else "m")
    if teor == "calma":
        return [(0.0, *IV)]
    if teor == "lenta":
        return [(0.0, *IV), (2.0, *iv)]
    if teor == "emotiva":
        return [(0.0, *iv)]
    if teor == "animada":
        return [(0.0, *IV), (2.0, (r0 + 7) % 12, "7")]
    return [(0.0, (r0 + 8) % 12, "maj"), (2.0, (r0 + 10) % 12, "maj")]   # épica: bVI -> bVII


def _pedal_por_acorde(harmonia, total):
    """Um pedal por acorde (troca na mudança de harmonia)."""
    saida = []
    for i, (o, _, _) in enumerate(harmonia):
        fim = harmonia[i + 1][0] if i + 1 < len(harmonia) else total
        if fim - o > EPS:
            saida.append((o, fim))
    return saida


def gerar_final(md_ev, acs, tipos, nivel, teor, inicio_musica=None, variacao=0):
    """Final que não existe na gravação: motivo do refrão (difícil), cadência do teor e
    acorde final na tônica (o 1º acorde da música). (direita, esquerda, cifras, info)."""
    if teor not in TEORES:
        raise ValueError(f"teor inválido: {teor} (use {', '.join(TEORES)})")
    total = 4.0 * COMPASSOS_FINAL[nivel]
    entrada = primeiro_acorde(acs, inicio_musica) or (0, "maj")
    r0 = entrada[0]
    maior = entrada[1] in ("maj", "7", "maj7", "6")
    tonica = (r0, "maj" if maior else "m")
    frase, como = achar_refrao(md_ev)
    compasso_frase = 4.0 * (frase[0][0] // 4)
    centro = REGISTRO[teor] + [0, 12, -12][(variacao // 3) % 3]
    motivo_tempos = total - 8.0                      # difícil: 2 compassos de motivo
    notas, harmonia = [], []
    mot = motivo(frase, max(4.0, motivo_tempos), compasso_frase)
    alturas = _no_registro([p for _, _, p in mot], centro) if mot else []
    mot = [(o, d, p) for (o, d, _), p in zip(mot, alturas)]
    if motivo_tempos > 0:
        base = acordes_em(acs, compasso_frase, compasso_frase + motivo_tempos) or [(0.0, *tonica)]
        if base[0][0] > EPS:
            base = [(0.0, base[0][1], base[0][2])] + base
        harmonia += base
        notas += [(o, d, p) for o, d, p in mot if o < motivo_tempos - EPS]
    cad0 = max(0.0, motivo_tempos)
    cad = [(cad0 + o, r, t) for o, r, t in _cadencia(teor, r0, maior)]
    harmonia += cad
    # compasso da cadência: contorno do motivo (1º compasso) preso às notas dos acordes
    for o, d, p in mot:
        if o >= 4.0 - EPS:
            break
        _, r, t = _acorde_no_tempo(cad, cad0 + o)
        alvo = min((_nota_perto(pc, p) for pc in _pcs(r, t, tipos)), key=lambda q: abs(q - p))
        notas.append((cad0 + o, min(d, 4.0 - o), alvo))
    if not any(o >= cad0 - EPS for o, _, _ in notas):
        notas.append((cad0, 4.0, _nota_perto((cad[0][1] + 4) % 12, centro)))
    final = cad0 + 4.0
    harmonia.append((final, *tonica))
    ultima = notas[-1][2] if notas else centro
    raiz_dir = _nota_perto(r0, ultima)
    if nivel != "dificil":   # acorde final sem linha suplementar demais pra ler
        while raiz_dir > 79:
            raiz_dir -= 12
        while raiz_dir < 60:
            raiz_dir += 12
    quinta = raiz_dir + 7
    if nivel == "facil":
        acorde_dir = [raiz_dir]
    elif nivel == "medio":
        acorde_dir = sorted({raiz_dir - 12 + tipos[tonica[1]][0][1], raiz_dir})   # 3ª abaixo da tônica
    else:
        acorde_dir = sorted({raiz_dir - 12, raiz_dir - 12 + tipos[tonica[1]][0][1], quinta - 12, raiz_dir})
    grave = 31 if teor == "epica" else 36
    baixo = grave + (r0 - grave % 12) % 12
    if nivel == "facil":
        acorde_esq = [baixo, baixo + 12] if teor == "epica" else [baixo if baixo >= 41 else baixo + 12]
    elif nivel == "medio":
        acorde_esq = [baixo, baixo + 7] + ([baixo + 12] if teor == "epica" else [])
    else:
        acorde_esq = [baixo, baixo + 7, baixo + 12]
    passo = 1.0 if nivel == "facil" else GRADE[nivel]
    corpo = _quantizar(notas, passo, final)
    direita = mao_direita(corpo, harmonia, teor, nivel, tipos)
    esquerda = _quantizar(mao_esquerda([h for h in harmonia if h[0] < final - EPS], final, teor, nivel, tipos, variacao),
                          passo, final)
    if teor == "animada":   # "ta-dá": dois golpes no acorde final
        direita += [(final, 1.0, acorde_dir), (final + 2, 2.0, acorde_dir)]
        esquerda += [(final, 1.0, acorde_esq), (final + 2, 2.0, acorde_esq)]
    else:
        direita.append((final, 4.0, acorde_dir))
        esquerda.append((final, 4.0, acorde_esq))
    cifras, ant = [], None
    for o, r, t in sorted({o: (o, r, t) for o, r, t in harmonia}.values()):
        if (r, t) != ant:
            cifras.append((o, r, t))
        ant = (r, t)
    din_ini, din_fim = DINAMICAS_FINAL[teor]
    info = dict(teor=teor, nivel=nivel, compassos=COMPASSOS_FINAL[nivel], variacao=variacao, refrao=como,
                tonica=dict(raiz=r0, tipo=tonica[1]),
                dinamicas=[(0.0, din_ini), (final, din_fim)],
                fermata=final if teor in COM_FERMATA else None,
                rit=cad0 if teor in COM_RIT else None,
                pedal=_pedal_por_acorde(sorted({o: (o, r, t) for o, r, t in harmonia}.values()), total)
                if teor in COM_PEDAL else [])
    return [(o, d, ps, None) for o, d, ps in direita], esquerda, cifras, info
