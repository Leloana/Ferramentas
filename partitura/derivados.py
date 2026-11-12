"""Fácil e difícil derivados do médio (proposta do usuário, 2026-11-10). Determinístico, sem LLM.

Revisão às cegas: o médio (sobretudo o Híbrido) é o mais bonito; o fácil "não parece a música" e o
difícil tem notas demais, soa artificial e fora do tom. Em vez de transcrever cada nível do zero,
o médio é a base:
- fácil = médio simplificado: direita com a melodia do médio (o ritmo real, só a nota de cima e
  sem as notas instrumentais rápidas); esquerda com uma nota grave por acorde, sustentada;
- difícil = médio enriquecido: na direita, 3ª/6ª do acorde embaixo das notas longas e oitava nos
  picos de frase; na esquerda, arpejo (baixo, notas do acorde, oitava) no lugar do acorde em
  bloco, com pedal em cada acorde, oitava no baixo das notas longas soltas e fermata no fim.
Eventos no formato do gerar.py: (offset_em_tempos, duração, [midis], *resto) — resto[0] = sílaba.
"""
from __future__ import annotations

import metrica


EPS = 1e-6


def notas_do_acorde(acs, tipos, off):
    """Só a tríade (fundamental, 3ª, 5ª): a 7ª/extensão detectada erra mais e, num arpejo ou numa
    nota acrescentada, soa como nota fora do tom."""
    for j, r, t, *_ in reversed(acs):
        if j <= off + 1e-6:
            if r is None or off >= j + 2:
                return set()
            return {(r + i) % 12 for i in tipos[t][0][:3]}
    return set()


def _silaba(ev):
    return ev[3] if len(ev) > 3 else None


# ------------------------------------------------------------------ fácil

# faixa da nota grave do fácil (MIDI): Fá2–Mi3, sem linha suplementar na clave de fá. Antes (36, 55),
# Dó2–Sol3: 64 músicas (lote.py, 2026-11-11) linhas suplementares na clave de fá 9,9 → 0 por 100 notas.
FACIL_BAIXO = (41, 52)

def facil_de_medio(md, me, acs, tipos, compasso=4.0):
    """(md, me, marcas) do fácil a partir do médio."""
    direita = []
    for ev in sorted(md, key=lambda e: e[0]):
        off, dur, ps = ev[0], ev[1], ev[2]
        if not ps:
            continue
        if not _silaba(ev) and dur < .5 - EPS:   # nota instrumental rápida sai
            continue
        novo = (off, dur, [max(ps)], *ev[3:])
        ant = direita[-1] if direita else None
        if ant and not _silaba(ev) and ant[2] == novo[2] and abs(ant[0] + ant[1] - off) < EPS:
            direita[-1] = (ant[0], ant[1] + dur, ant[2], *ant[3:])   # repetida sem sílaba: segura
            continue
        direita.append(novo)
    # esquerda: uma nota grave por trecho de acorde (e por compasso), sustentada
    me = sorted(me, key=lambda e: e[0])
    if not me:
        return direita, [], []
    ini, fim = me[0][0], max(e[0] + e[1] for e in me)
    trocas = sorted({j for j, r, *_ in acs if r is not None and ini - EPS <= j < fim}
                    | {compasso * k for k in range(int(ini // compasso), int(fim // compasso) + 2)
                       if ini - EPS <= compasso * k < fim})
    esquerda = []
    for a, b in zip(trocas, trocas[1:] + [fim]):
        soando = [p for o, d, ps, *_ in me for p in ps if o < b - EPS and o + d > a + EPS]
        if not soando:
            continue
        baixo = min(soando)
        while baixo < FACIL_BAIXO[0]:
            baixo += 12
        while baixo > FACIL_BAIXO[1]:
            baixo -= 12
        ant = esquerda[-1] if esquerda else None
        if ant and ant[2] == [baixo] and abs(ant[0] + ant[1] - a) < EPS and (a % compasso) > EPS:
            esquerda[-1] = (ant[0], ant[1] + (b - a), ant[2])
        else:
            esquerda.append((a, b - a, [baixo]))
    return direita, esquerda, []


# ------------------------------------------------------------------ difícil

def _juntar_iguais(me):
    """Notas soltas iguais e coladas (Si♭ Si♭ Si♭ em colcheias) viram uma nota longa."""
    saida = []
    for ev in sorted(me, key=lambda e: e[0]):
        ant = saida[-1] if saida else None
        if (ant and len(ev[2]) == 1 and ant[2] == list(ev[2]) and abs(ant[0] + ant[1] - ev[0]) < EPS
                and (ev[0] % metrica.TEMPOS) > EPS):          # não atravessa a barra: o arpejo recomeça no compasso
            saida[-1] = (ant[0], ant[1] + ev[1], ant[2])
        else:
            saida.append((ev[0], ev[1], list(ev[2])))
    return saida


def _nota_do_acorde_abaixo(p, pcs, minimo=3, maximo=9, alvo=4):
    cands = [q for q in range(p - maximo, p - minimo + 1) if q % 12 in pcs]
    return min(cands, key=lambda q: abs((p - q) - alvo)) if cands else None


# enriquecimentos do difícil (lote.py --ajustes '{"derivados.DIFICIL": {...}}' liga/desliga cada um).
# evitar_choque: a nota acrescentada não pode formar 2ª/9ª menor com a outra mão soando junto
# (64 músicas, 2026-11-11: choques do difícil 1,53 → 0,24 por 100 ataques, nada piorou).
DIFICIL = dict(tercas=True, oitava_pico=True, arpejo=True, baixo_oitava=True, evitar_choque=True)


def _choca(x, outras, acima: bool):
    """x forma 2ª/9ª menor com alguma de `outras` (acima=True: as outras estão acima de x)."""
    return any(((o - x) if acima else (x - o)) > 0 and ((o - x) if acima else (x - o)) % 12 == 1 for o in outras)


def _soando(ev, ini, fim):
    return [p for o, d, ps, *_ in ev for p in ps if o < fim - EPS and ini < o + d - EPS]


def dificil_de_medio(md, me, acs, tipos, bpm, faixa_esq=None):
    """(md, me, marcas) do difícil a partir do médio."""
    if faixa_esq is None:
        from niveis import GRAVE_MINIMO
        faixa_esq = (GRAVE_MINIMO, 64)
    md = sorted(md, key=lambda e: e[0])
    topo = [max(e[2]) if e[2] else None for e in md]
    direita = []
    for i, ev in enumerate(md):
        off, dur, ps = ev[0], ev[1], list(ev[2])
        if ps and dur >= 1 - EPS:
            p = max(ps)
            viz = [t for t in topo[max(0, i - 4):i + 5] if t is not None]
            if DIFICIL["oitava_pico"] and dur >= 2 - EPS and p >= max(viz) and p - 12 >= 55:
                ps = sorted(set(ps) | {p - 12})                     # pico de frase: oitava
            elif DIFICIL["tercas"]:
                q = _nota_do_acorde_abaixo(p, notas_do_acorde(acs, tipos, off))
                if q is not None and DIFICIL["evitar_choque"] and _choca(q, _soando(me, off, off + dur), acima=False):
                    q = None
                if q is not None and q >= 55:
                    ps = sorted(set(ps) | {q})                      # 3ª/6ª do acorde embaixo
        direita.append((off, dur, ps, *ev[3:]))
    passo = .5 if bpm <= 140 else 1.0
    esquerda, marcas = [], []
    for off, dur, ps, *r in _juntar_iguais(me):
        ps = sorted(ps)
        if not DIFICIL["arpejo"]:
            if DIFICIL["baixo_oitava"] and len(ps) == 1 and dur >= 2 - EPS and ps[0] - 12 >= faixa_esq[0]:
                esquerda.append((off, dur, [ps[0] - 12, ps[0]]))
            else:
                esquerda.append((off, dur, ps, *r))
            continue
        if len(ps) == 1 and dur >= 1 - EPS:   # nota solta (ou repetida) longa: arpejo do acorde a partir dela
            pcs = notas_do_acorde(acs, tipos, off)
            acima = [q for q in range(ps[0] + 1, ps[0] + 17) if q % 12 in pcs and q <= faixa_esq[1]][:3]
            if len(acima) >= 2:
                ps = ps + acima
        if len(ps) >= 2 and dur >= 1 - EPS:
            subida = ps + ([ps[0] + 12] if ps[0] + 12 <= faixa_esq[1] and ps[0] + 12 not in ps else [])
            padrao = subida + subida[-2:0:-1]                       # sobe e desce sem repetir a ponta
            t, k = off, 0
            while t < off + dur - EPS:
                d = min(passo, off + dur - t)
                x = padrao[k % len(padrao)]
                if DIFICIL["evitar_choque"] and _choca(x, _soando(direita, t, t + d), acima=True):
                    x = ps[0]                                       # choca com a direita: volta ao baixo
                esquerda.append((t, d, [x]))
                t += d
                k += 1
            marcas.append((off, "pedal", off + dur))
        elif DIFICIL["baixo_oitava"] and len(ps) == 1 and dur >= 2 - EPS and ps[0] - 12 >= faixa_esq[0]:
            esquerda.append((off, dur, [ps[0] - 12, ps[0]]))         # baixo longo em oitava
        else:
            esquerda.append((off, dur, ps, *r))
    if direita:
        marcas.append((direita[-1][0], "fermata", None))
    return direita, esquerda, marcas
