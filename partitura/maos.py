"""Tocabilidade e dedilhado: modelo da mão, sem LLM e sem modelo treinado.

Cada mão é resolvida por programação dinâmica sobre os instantes de ataque. O estado é
qual dedo está em cada nota que soa naquele instante; nota segurada (ligada ou longa)
mantém o dedo e prende a mão no lugar, então as notas novas precisam caber junto com ela.

Limites entre pares de dedos: tabela de Parncutt et al. (1997) com a revisão de
Jacobs (2001), em semitons, escalada pelo tamanho de mão de cada nível.

Um trecho é intocável quando nenhuma digitação cabe:
- abertura: notas simultâneas não cabem na mão;
- dedos: mais notas soando do que dedos livres;
- ligada: a mão precisa mudar de lugar enquanto uma nota continua segurada;
- salto: a mão muda de lugar mais rápido do que o nível permite.

`tornar_tocavel` corrige esses trechos mudando só o acompanhamento (oitava de um
acorde, nota do acorde, duração de nota segurada). Nota protegida (melodia cantada)
nunca muda; quando o problema é só dela, fica registrado e a nota fica como está.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left
from itertools import combinations

PRETAS = {1, 3, 6, 8, 10}

# (MinPrac, MinComf, MinRel, MaxRel, MaxComf, MaxPrac) em semitons, mão direita,
# dedo a na primeira nota e dedo b na segunda (a < b). Negativo = b abaixo de a
# (só com polegar: passagem do polegar por baixo / dedo por cima).
TABELA = {
    (1, 2): (-5, -3, 1, 5, 8, 10), (1, 3): (-4, -2, 3, 7, 10, 12),
    (1, 4): (-3, -1, 5, 9, 12, 14), (1, 5): (-1, 1, 7, 10, 13, 15),
    (2, 3): (1, 1, 1, 2, 3, 5), (2, 4): (1, 1, 3, 4, 5, 7), (2, 5): (2, 2, 5, 6, 8, 10),
    (3, 4): (1, 1, 1, 2, 2, 4), (3, 5): (1, 1, 3, 4, 5, 7), (4, 5): (1, 1, 1, 2, 3, 5),
}

# abertura: maior intervalo polegar-mínimo (semitons). base/vel: tempo pra mudar a mão
# de lugar = base + distância/vel (s, semitons/s). mostrar: quais dedos vão pra partitura.
PERFIL = {
    "facil": dict(abertura=12, base=.35, vel=24, mostrar="todos"),
    "medio": dict(abertura=12, base=.22, vel=40, mostrar="mudancas"),
    "dificil": dict(abertura=13, base=.12, vel=70, mostrar="mudancas"),
}
FAIXA = {"direita": (53, 98), "esquerda": (28, 67)}
FAIXA_FACIL_ESQ = (36, 64)
INVIAVEL = 1000.0
EPS = 1e-6


@dataclass(eq=False)
class Nota:
    id: int
    ini: float      # tempos (semínimas)
    fim: float
    p: int
    ev: int         # índice do evento de origem
    protegida: bool


def _tabela(abertura: int) -> dict:
    f = abertura / 15
    saida = {}
    for par, (mnp, mnc, mnr, mxr, mxc, mxp) in TABELA.items():
        # o tamanho da mão muda a abertura a partir do polegar; entre dedos vizinhos quase não muda
        def esc(v, par=par):
            return v if (abs(v) <= 1 or par[0] != 1) else round(v * f)
        saida[par] = (esc(mnp), esc(mnc), mnr, mxr, min(esc(mxc), esc(mxp)), esc(mxp))
    return saida


class Mao:
    def __init__(self, lado: str, nivel: str, bpm: float):
        self.lado = lado
        self.perfil = PERFIL[nivel]
        self.tab = _tabela(self.perfil["abertura"])
        self.spb = 60.0 / max(bpm, 1.0)
        self.nivel = nivel

    # pitch orientado: na esquerda o dedo 1 fica em cima, então espelha
    def o(self, p: int) -> int:
        return p if self.lado == "direita" else -p

    def par(self, fa, pa, fb, pb, simultaneo):
        """(violação em semitons, custo) de tocar pa com fa e pb com fb."""
        if fa < fb:
            lin, d, polegar = self.tab[(fa, fb)], self.o(pb) - self.o(pa), fa == 1
        else:
            lin, d, polegar = self.tab[(fb, fa)], self.o(pa) - self.o(pb), fb == 1
        mnp, mnc, mnr, mxr, mxc, mxp = lin
        if simultaneo:
            mnp, mnc = max(mnp, 1), max(mnc, 1)
        viol = max(0, d - mxp, mnp - d)
        peso = 1 if polegar else 2
        custo = 2 * max(0, d - mxc, mnc - d) + peso * max(0, d - mxr) + peso * max(0, mnr - d) * (.5 if simultaneo else 1)
        return viol, custo

    def custo_dedo(self, f, p):
        preta = p % 12 in PRETAS
        return (1.0 if f == 4 else 0) + (1.0 if f == 5 and preta else 0) + (2.0 if f == 1 and preta else 0)

    def centro(self, pares):
        # posição da mão: cada dedo fica ~2 semitons do vizinho, dedo 3 no centro
        return sum(self.o(n.p) - 2 * (f - 3) for n, f in pares) / len(pares)


def _instantes(notas):
    inis = sorted({round(n.ini, 6) for n in notas})
    return inis


def _atribuicoes(mao: Mao, novas, presas):
    """Gera (pares, violação vertical, custo, tipo) pra notas novas dados os dedos presos."""
    usados = {f for _, f in presas}
    livres = [f for f in range(1, 6) if f not in usados]
    novas = sorted(novas, key=lambda n: mao.o(n.p))
    if len(novas) > len(livres):
        return None
    saida = []
    for combo in combinations(livres, len(novas)):
        pares = list(presas) + list(zip(novas, combo))
        ordem = sorted(pares, key=lambda nf: (mao.o(nf[0].p), nf[1]))
        if any(a[1] >= b[1] for a, b in zip(ordem, ordem[1:])):
            continue
        viol, custo = 0, 0.0
        for i in range(len(ordem)):
            n, f = ordem[i]
            custo += mao.custo_dedo(f, n.p) if (n, f) not in presas else 0
            for j in range(i + 1, len(ordem)):
                v, c = mao.par(f, n.p, ordem[j][1], ordem[j][0].p, True)
                viol += v
                custo += c
        saida.append((tuple(pares), viol, custo))
    return saida


def dedilhar(mao: Mao, notas: list[Nota]):
    """Melhor digitação da sequência. Devolve (dedo por nota.id, problemas, mudanças, custo)."""
    if not notas:
        return {}, [], set(), 0.0
    inis = _instantes(notas)
    por_ini = {}
    for n in notas:
        por_ini.setdefault(round(n.ini, 6), []).append(n)
    camadas = []  # cada camada: lista de estados (pares, custo_acum, back, info)
    for k, t in enumerate(inis):
        novas = por_ini[t]
        estados = {}
        anteriores = camadas[-1] if camadas else [((), 0.0, None, None)]
        t_ant = inis[k - 1] if k else None
        memo = {}  # mesmas presas -> mesmas opções (quase sempre nenhuma presa)
        for ia, (pares_ant, custo_ant, _, _) in enumerate(anteriores):
            presas = tuple((n, f) for n, f in pares_ant if n.fim > t + EPS)
            chave_p = tuple((n.id, f) for n, f in presas)
            if chave_p not in memo:
                memo[chave_p] = _atribuicoes(mao, novas, presas)
            opcoes = memo[chave_p]
            tipo_extra = None
            if not opcoes:
                # não cabe com as presas: solta as presas (problema) e tenta de novo
                tipo_extra = "dedos" if len(novas) + len(presas) > 5 else "ligada"
                presas = ()
                if "solto" not in memo:
                    memo["solto"] = _atribuicoes(mao, novas[:5], ()) or []
                opcoes = memo["solto"]
                if not opcoes:
                    continue
            for pares, viol_v, custo_v in opcoes:
                custo = custo_v
                prob = []
                if tipo_extra:
                    prob.append((tipo_extra, 1))
                    custo += INVIAVEL
                if viol_v:
                    prob.append(("abertura", viol_v))
                    custo += INVIAVEL + 10 * viol_v
                mudou = False
                if pares_ant:
                    atacadas = [(n, f) for n, f in pares if (n, f) not in presas]
                    soltas = [(n, f) for n, f in pares_ant if (n, f) not in presas]
                    viol_h, custo_h = 0, 0.0
                    for na, fa in soltas:
                        for nb, fb in atacadas:
                            if fa == fb:
                                if na.p != nb.p:
                                    # mesmo dedo em outra tecla: a mão tem que levantar e ir
                                    viol_h = max(viol_h, abs(na.p - nb.p))
                                    custo_h += 2
                                continue
                            v, c = mao.par(fa, na.p, fb, nb.p, False)
                            if na.p == nb.p:
                                c += 1.5  # troca de dedo na nota repetida
                            viol_h = max(viol_h, v)
                            custo_h += c
                            cruza = (fa < fb) != (mao.o(nb.p) > mao.o(na.p)) and mao.o(nb.p) != mao.o(na.p)
                            if cruza:
                                custo_h += 1 + (1 if (fa == 1 and na.p % 12 in PRETAS) or (fb == 1 and nb.p % 12 in PRETAS) else 0)
                                mudou = True
                            if fa == 3 and fb == 4:
                                custo_h += 1
                    custo += custo_h
                    if atacadas and soltas:
                        dist = abs(mao.centro(atacadas) - mao.centro(soltas))
                        custo += .1 * dist
                        # com nota segurada a mão gira em volta dela: o alcance já foi
                        # conferido junto com as presas, não há mudança de lugar
                        if viol_h and not presas:
                            mudou = True
                            if True:
                                precisa = mao.perfil["base"] + dist / mao.perfil["vel"]
                                tem = (t - t_ant) * mao.spb
                                if tem + EPS < precisa:
                                    prob.append(("salto", round(precisa - tem, 3)))
                                    custo += INVIAVEL + 100 * (precisa - tem)
                                else:
                                    # mudar de lugar custa pelo aperto: com pausa longa é quase de graça
                                    custo += .5 + 3 * precisa / tem + .05 * dist
                                    # legato: a nota anterior ia até perto daqui, a mão solta antes
                                    folga = (t - max(n.fim for n, _ in soltas)) * mao.spb
                                    if folga + EPS < precisa:
                                        custo += 1
                total = custo_ant + custo
                chave = tuple(sorted((n.id, f) for n, f in pares))
                if chave not in estados or total < estados[chave][1]:
                    estados[chave] = (pares, total, ia, (prob, mudou))
        camadas.append(list(estados.values()))
    # volta
    fim = camadas[-1]
    i = min(range(len(fim)), key=lambda j: fim[j][1])
    custo_total = fim[i][1]
    dedos, problemas, mudancas = {}, [], set()
    for k in range(len(camadas) - 1, -1, -1):
        pares, _, back, (prob, mudou) = camadas[k][i]
        for n, f in pares:
            dedos.setdefault(n.id, f)
        for tipo, mag in prob:
            problemas.append(dict(instante=inis[k], tipo=tipo, intensidade=mag,
                                  notas=sorted(n.p for n, f in pares)))
        if mudou or k == 0:
            mudancas.add(inis[k])
        i = back
    problemas.sort(key=lambda p: p["instante"])
    return dedos, problemas, mudancas, custo_total


# ---------------------------------------------------------------- eventos <-> notas

def _notas(ev, protegidas, mao_lado):
    notas = []
    for i, (off, dur, ps, *_) in enumerate(ev):
        for p in ps:
            notas.append(Nota(len(notas), off, off + dur, p, i,
                              (round(off, 6), p) in protegidas))
    return notas


def _ancora(ps, prot, lado):
    if prot:
        return max(prot) if lado == "direita" else min(prot)
    return max(ps) if lado == "direita" else min(ps)


def _janela(ev, i, raio=6):
    return max(0, i - raio), min(len(ev), i + raio + 1)


def _pontuar(mao, ev, a, b, protegidas):
    notas = _notas(ev[a:b], protegidas, mao.lado)
    _, probs, _, custo = dedilhar(mao, notas)
    return len(probs), custo, probs


class _Outra:
    """Eventos da outra mão com busca por tempo (ordenados pelo ataque)."""
    def __init__(self, ev):
        self.ev = sorted(ev, key=lambda e: e[0])
        self.inis = [e[0] for e in self.ev]
        self.maior_dur = max((e[1] for e in self.ev), default=0)

    def soando(self, off, fim):
        a = bisect_left(self.inis, off - self.maior_dur - EPS)
        b = bisect_left(self.inis, fim - EPS)
        return [e for e in self.ev[a:b] if e[0] + e[1] > off + EPS]


def _colide(ev_cand, i, outra, lado):
    """Nota da esquerda em cima (ou na mesma tecla) de nota da direita que soa junto."""
    off, dur, ps, *_ = ev_cand[i]
    for o2, d2, ps2, *_ in outra.soando(off, off + dur):
        if ps2:
            if lado == "esquerda" and max(ps) >= min(ps2):
                return True
            if lado == "direita" and min(ps) <= max(ps2):
                return True
    return False


def _candidatos(ev, i, ant, tipos, protegidas, lado, faixa):
    """Versões alternativas do trecho: (descrição, peso da mudança musical, eventos)."""
    saida = []

    def troca(j, ps, desc, peso):
        novo = list(ev)
        off, dur, _, *r = ev[j]
        novo[j] = (off, dur, sorted(ps), *r)
        saida.append((desc, peso, novo))

    def prot(j):
        off = round(ev[j][0], 6)
        return [p for p in ev[j][2] if (off, p) in protegidas]

    alvos = [i] + ([ant] if ant is not None else [])
    for j in alvos:
        ps = list(ev[j][2])
        pr = prot(j)
        livres = [p for p in ps if p not in pr]
        if not livres:
            continue
        anc = _ancora(ps, pr, lado)
        if tipos & {"abertura", "dedos"}:
            fechado = sorted({p if p in pr else (anc - (anc - p) % 12 if lado == "direita"
                                                  else anc + (p - anc) % 12) for p in ps})
            if fechado != sorted(ps):
                troca(j, fechado, "fecha o acorde", 1)
            # fechar pode afastar do vizinho: fecha e já leva pra oitava mais perto dele
            viz = [ev[k][2] for k in (j - 1, j + 1) if 0 <= k < len(ev) and k != j]
            if viz and not pr:
                alvo = sum(sum(v) / len(v) for v in viz) / len(viz)
                c = sum(fechado) / len(fechado)
                for k in (12, -12):
                    if (abs(c + k - alvo) < abs(c - alvo) and faixa[0] <= min(fechado) + k
                            and max(fechado) + k <= faixa[1]):
                        troca(j, [p + k for p in fechado], f"fecha o acorde e muda {k:+d} semitons", 3)
        if len(ps) > 1:
            if not pr and len(ps) >= 2:
                troca(j, [anc], "deixa só a nota principal", 3 * (len(ps) - 1))
            dist = sorted(livres, key=lambda p: -abs(p - anc))
            for p in dist[:2]:
                if p != anc:
                    troca(j, [q for q in ps if q != p], f"tira a nota {p}", 3)
        if not pr and tipos & {"salto", "ligada"}:
            ref = ev[ant if j == i else i][2] if ant is not None else ps
            alvo_c = sum(ref) / len(ref)
            c = sum(ps) / len(ps)
            for k in (12, -12, 24, -24):
                if abs((c + k) - alvo_c) < abs(c - alvo_c) and faixa[0] <= min(ps) + k and max(ps) + k <= faixa[1]:
                    troca(j, [p + k for p in ps], f"muda {k:+d} semitons", 2 if abs(k) == 12 else 4)
                    break
    if "ligada" in tipos and ant is not None:
        off, dur, ps, *r = ev[ant]
        novo_fim = ev[i][0]
        if novo_fim - off > EPS and not prot(ant):
            novo = list(ev)
            novo[ant] = (off, novo_fim - off, ps, *r)
            saida.append(("solta a nota segurada", 1, novo))
    return saida


def corrigir_mao(mao: Mao, ev, protegidas, outra=(), max_passos=5000):
    """Corrige os trechos intocáveis de uma mão. Devolve (eventos, correções)."""
    ev = sorted(ev, key=lambda e: e[0])
    faixa = FAIXA_FACIL_ESQ if (mao.lado == "esquerda" and mao.nivel == "facil") else FAIXA[mao.lado]
    outra = _Outra(outra)
    correcoes = []
    passos = 0
    for _rodada in range(3):  # uma correção pode revelar o problema seguinte
        _, probs, _, _ = dedilhar(mao, _notas(ev, protegidas, mao.lado))
        fila = sorted({p["instante"] for p in probs})
        if not fila:
            break
        antes = len(correcoes)
        ev, passos = _rodada_correcao(mao, ev, protegidas, outra, faixa, fila, correcoes, passos, max_passos)
        if len(correcoes) == antes:
            break
    return ev, correcoes


def _rodada_correcao(mao, ev, protegidas, outra, faixa, fila, correcoes, passos, max_passos):
    inis = [e[0] for e in ev]  # as correções não mudam ataques, só notas e durações
    for t in fila:
        if passos >= max_passos:
            break
        idx = bisect_left(inis, t - EPS)
        if idx >= len(ev) or abs(ev[idx][0] - t) > EPS:
            continue
        a, b = _janela(ev, idx)
        base_n, base_c, pj = _pontuar(mao, ev, a, b, protegidas)
        if base_n == 0:
            continue
        aqui = [p for p in pj if abs(p["instante"] - t) < EPS]
        if not aqui:
            continue
        tipos = {p["tipo"] for p in aqui}
        tipo = "+".join(sorted(tipos))
        ant = idx - 1 if idx > 0 else None
        melhor = None
        for desc, peso, cand in _candidatos(ev, idx, ant, tipos, protegidas, mao.lado, faixa):
            mudados = [j for j in (idx, ant) if j is not None and cand[j] != ev[j]]
            if any(_colide(cand, j, outra, mao.lado) for j in mudados):
                continue
            n, c, _ = _pontuar(mao, cand, a, b, protegidas)
            # menor mudança musical primeiro; custo da mão só desempata
            if n < base_n and (melhor is None or (n, peso, c) < melhor[0]):
                melhor = ((n, peso, c), desc, cand, mudados)
        passos += 1
        if melhor:
            _, desc, cand, mudados = melhor
            for j in mudados:
                correcoes.append(dict(instante=round(ev[j][0], 4), tipo=tipo, acao=desc,
                                      antes=list(ev[j][2]), depois=list(cand[j][2]),
                                      dur_antes=ev[j][1], dur_depois=cand[j][1]))
            ev = cand
    return ev, passos


# menor nota (MIDI) em que cada intervalo ainda soa claro no piano ("low interval limits");
# mesma tabela de metricas.LIMITE_GRAVE
LIMITE_GRAVE = {1: 52, 2: 51, 3: 48, 4: 46, 5: 45, 6: 46, 7: 34, 8: 41, 9: 41, 10: 41, 11: 41}
# custo de tirar uma voz pelo intervalo até o baixo: a 5ª é a que menos faz falta, a 3ª a que mais
CUSTO_TIRAR = {7: 1, 0: 1, 10: 2, 11: 2, 3: 3, 4: 3}


def embolados(ps):
    """Pares vizinhos abaixo do limite de clareza do grave."""
    ps = sorted(set(ps))
    return sum(1 for a, b in zip(ps, ps[1:]) if b - a in LIMITE_GRAVE and a < LIMITE_GRAVE[b - a])


def clarear_grave(me, protegidas=frozenset()):
    """Tira da esquerda a voz que embola no grave (terça abaixo de Dó3 etc.).

    Fechar o acorde pra caber na mão põe 3ª/7ª logo acima de um baixo grave; ali o
    intervalo vira ruído. O baixo e as notas protegidas ficam; das outras, tira o
    conjunto mais barato (5ª antes de 7ª antes de 3ª) que acaba com o embolado.
    """
    saida, correcoes = [], []
    for off, dur, ps, *r in me:
        ps = sorted(set(ps))
        if len(ps) < 2 or not embolados(ps):
            saida.append((off, dur, ps, *r))
            continue
        baixo = ps[0]
        fixas = {baixo} | {p for p in ps if (round(off, 6), p) in protegidas}
        livres = [p for p in ps if p not in fixas]
        melhor = None
        for k in range(len(livres) + 1):
            for tirar in combinations(livres, k):
                resto = [p for p in ps if p not in tirar]
                custo = (embolados(resto), sum(CUSTO_TIRAR.get((p - baixo) % 12, 2) for p in tirar), k)
                if melhor is None or custo < melhor[0]:
                    melhor = (custo, resto)
        resto = melhor[1]
        if resto != ps and embolados(resto) < embolados(ps):
            correcoes.append(dict(instante=round(off, 4), tipo="grave", acao="tira a voz que embola no grave",
                                  antes=ps, depois=resto))
            ps = resto
        saida.append((off, dur, ps, *r))
    return saida, correcoes


def separar_maos(md, me, nivel, protegidas):
    """Esquerda não pode tocar em cima da direita no mesmo instante: desce a oitava ou tira a nota."""
    lo = (FAIXA_FACIL_ESQ if nivel == "facil" else FAIXA["esquerda"])[0]
    saida, correcoes = [], []
    for i, (off, dur, ps, *r) in enumerate(sorted(me, key=lambda e: e[0])):
        topo_dir = [min(ps2) for o2, d2, ps2, *_ in md if ps2 and o2 < off + dur - EPS and off < o2 + d2 - EPS]
        novo = list(ps)
        if topo_dir:
            limite = min(topo_dir)
            if max(novo) >= limite:
                baixo = min(novo)
                if baixo < limite:
                    # fecha em volta do baixo e tira só o que ainda encosta na direita
                    fechado = sorted({baixo + (p - baixo) % 12 for p in novo})
                    novo = [p for p in fechado if p < limite]
                elif baixo - 12 >= lo:
                    novo = [p - 12 for p in sorted({baixo + (p - baixo) % 12 for p in novo})]
                    novo = [p for p in novo if p < limite] or [baixo - 12]
        if novo != list(ps):
            correcoes.append(dict(instante=round(off, 4), tipo="maos", acao="esquerda abaixo da direita",
                                  antes=list(ps), depois=sorted(novo)))
        saida.append((off, dur, sorted(novo), *r))
    return saida, correcoes


def tornar_tocavel(md, me, nivel, bpm, protegidas=frozenset(), corrigir=True, mostrar=None, clarear=True):
    """Corrige as duas mãos e calcula os dedos.

    md/me: eventos (offset, duração, [midis], *resto) em tempos.
    protegidas: {(offset arredondado a 6 casas, midi)} das notas que não podem mudar.
    clarear: tira da esquerda a voz que embola no grave (`clarear_grave`).
    Devolve (md, me, dedos_md, dedos_me, relatório); dedos_* têm uma entrada por evento:
    lista de dedos na ordem de sorted(ps), ou None quando o dedo não vai pra partitura.
    """
    mostrar = mostrar or PERFIL[nivel]["mostrar"]
    rel = dict(nivel=nivel, correcoes=[], restantes=[], mudancas_de_posicao={})
    md = sorted(md, key=lambda e: e[0])
    me = sorted(me, key=lambda e: e[0])
    if corrigir:
        me, c = separar_maos(md, me, nivel, protegidas)
        rel["correcoes"] += [dict(mao="esquerda", **x) for x in c]
    maos = {"direita": Mao("direita", nivel, bpm), "esquerda": Mao("esquerda", nivel, bpm)}
    if corrigir:
        md, c = corrigir_mao(maos["direita"], md, protegidas, me)
        rel["correcoes"] += [dict(mao="direita", **x) for x in c]
        me, c = corrigir_mao(maos["esquerda"], me, protegidas, md)
        rel["correcoes"] += [dict(mao="esquerda", **x) for x in c]
        if clarear:
            me, c = clarear_grave(me, protegidas)
            rel["correcoes"] += [dict(mao="esquerda", **x) for x in c]
    dedos_saida = {}
    for lado, ev in (("direita", md), ("esquerda", me)):
        notas = _notas(ev, protegidas, lado)
        dedos, probs, mudancas, _ = dedilhar(maos[lado], notas)
        rel["restantes"] += [dict(mao=lado, protegida=any((round(p["instante"], 6), q) in protegidas
                                                         for q in p["notas"]), **p) for p in probs]
        rel["mudancas_de_posicao"][lado] = len(mudancas)
        por_ev = {}
        for n in notas:
            por_ev.setdefault(n.ev, []).append((n.p, dedos.get(n.id)))
        lista, fim_ant = [], None
        for i, (off, dur, ps, *_) in enumerate(ev):
            fs = [f for _, f in sorted(por_ev.get(i, []))]
            pausa = fim_ant is None or off - fim_ant >= 1 - EPS
            mostra = mostrar == "todos" or (mostrar == "mudancas" and (round(off, 6) in mudancas or pausa))
            lista.append(fs if (mostra and fs and None not in fs) else None)
            fim_ant = off + dur
        dedos_saida[lado] = lista
    rel["resumo"] = dict(
        corrigidos=len(rel["correcoes"]),
        restantes=len(rel["restantes"]),
        restantes_na_melodia=sum(1 for p in rel["restantes"] if p["protegida"]),
    )
    return md, me, dedos_saida["direita"], dedos_saida["esquerda"], rel
