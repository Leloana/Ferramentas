"""Choques entre a melodia cantada e o acompanhamento (frente 3 da PROXIMA_ETAPA).

"Tocável mas estranho": a voz sustenta uma nota que fica a um semitom de uma nota do
acompanhamento (Si cantado sobre Sib da mão esquerda num C7). Duas correções, nesta
ordem, sempre com a melodia forte como evidência (nota de >= 1 tempo):

1. `corrigir_qualidade`: troca a qualidade do acorde detectado dentro da mesma família
   (maior: maj/7/maj7/6; menor: m/m7/m6) pela que contém a nota cantada e muda menos
   notas. O detector por croma confunde 7 com 7M e 6 com 7M; a voz sustentada desempata.
   Família não muda (Mib cantado sobre Dó maior pode ser blue note, não vira Dó menor).
2. `tirar_choques`: no acompanhamento já montado, tira a voz que forma semitom com a
   nota cantada (não o baixo), como o pianista que tira a terça debaixo de uma melodia
   em sus4. Tensões que não formam semitom (9ª, 13ª) ficam.

Sem LLM: classes de altura, duração e sobreposição no tempo. Tudo registrado.
"""
from __future__ import annotations

FAMILIA = {
    "maj": "maior", "7": "maior", "maj7": "maior", "6": "maior",
    "m": "menor", "m7": "menor", "m6": "menor",
}
FORTE = 1.0      # tempos: nota cantada que conta como evidência
EPS = 1e-6


def _pcs(r, tipo, tipos):
    return {(r + i) % 12 for i in tipos[tipo][0]}


def _choca(pc, pcs):
    """pc não está no acorde e fica a um semitom de alguma nota dele."""
    return pc not in pcs and any((pc - q) % 12 in (1, 11) for q in pcs)


def melodia_forte(notas_q, ini, fim):
    """Classes de altura cantadas com >= FORTE tempos dentro de [ini, fim)."""
    peso = {}
    for a, b, p, *_ in notas_q:
        sobra = min(b, fim) - max(a, ini)
        if sobra > EPS and b - a >= FORTE - EPS:
            peso[p % 12] = peso.get(p % 12, 0) + sobra
    return peso


def corrigir_qualidade(acs, notas_q, tipos, janela=2):
    """acs: (pos, raiz, tipo, baixo). Devolve (acs corrigidos, mudanças)."""
    saida, mudancas = [], []
    for j, r, t, *resto in acs:
        if r is None or t not in FAMILIA:
            saida.append((j, r, t, *resto))
            continue
        pcs = _pcs(r, t, tipos)
        forte = melodia_forte(notas_q, j, j + janela)
        chocam = [pc for pc in forte if _choca(pc, pcs)]
        novo = t
        if chocam:
            alvo = max(chocam, key=lambda pc: forte[pc])
            cands = [u for u in tipos if FAMILIA.get(u) == FAMILIA[t] and alvo in _pcs(r, u, tipos)
                     and not any(_choca(pc, _pcs(r, u, tipos)) for pc in forte)]
            if cands:
                novo = min(cands, key=lambda u: (len(_pcs(r, u, tipos) ^ pcs), len(tipos[u][0])))
        if novo != t:
            mudancas.append(dict(pos=j, raiz=r, antes=t, depois=novo,
                                 melodia=sorted(chocam)))
        saida.append((j, r, novo, *resto))
    return saida, mudancas


def tirar_choques(md, me):
    """Tira do acompanhamento (esquerda) a voz a um semitom da nota cantada forte que soa junto.

    md/me: eventos (offset, dur, [midis], *resto) em tempos. Baixo (nota mais grave) fica.
    Devolve (me, mudanças).
    """
    fortes = [(o, o + d, ps) for o, d, ps, *_ in md if d >= FORTE - EPS]
    saida, mudancas = [], []
    for o, d, ps, *resto in me:
        if len(ps) < 2:
            saida.append((o, d, ps, *resto))
            continue
        cantadas = {p % 12 for a, b, qs in fortes if a < o + d - EPS and o < b - EPS for p in qs}
        baixo = min(ps)
        pcs_acomp = {p % 12 for p in ps}
        tirar = [p for p in ps if p != baixo
                 and any((c - p) % 12 in (1, 11) and c not in pcs_acomp for c in cantadas)]
        if tirar:
            novo = [p for p in ps if p not in tirar]
            mudancas.append(dict(instante=round(o, 4), antes=list(ps), depois=novo,
                                 melodia=sorted(cantadas)))
            saida.append((o, d, novo, *resto))
        else:
            saida.append((o, d, ps, *resto))
    return saida, mudancas
