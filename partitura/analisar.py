"""Compara todas as partituras geradas (música × versão × nível) com métricas objetivas.

  python analisar.py            -> tabela no terminal + saida/analise.json

Métricas (por partitura):
  letra%      palavras da letra oficial (LRCLIB/arquivo) que aparecem embaixo das notas, em ordem
  md n/s      notas por segundo na mão direita (tempo da partitura)     | tocabilidade
  me n/s      notas por segundo na mão esquerda                         |
  acorde      média de notas por ataque (as duas mãos)                  |
  abertura    % de acordes com abertura > 1 oitava numa mão             |
  saltos      salto médio da nota mais grave da mão esquerda (semitons) |
  acid%       % de notas com acidente fora da armadura                  |
  harmonia%   % das notas que pertencem à cifra do momento (coerência com a música)
  melodia%    % dos tempos em que a nota mais aguda bate com a melodia cantada (mesma classe de altura)
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
SAIDA = AQUI / "saida"
NIVEIS = ["Facil", "Medio", "Dificil"]
VERSOES = ["Acordes", "Hibrido", "HibridoAMT", "Pop2Piano", "AMT-APC"]
ARTISTA = {"Chega de Saudade": None, "Baby": "Justin Bieber", "Bandido com Bandida": "DPAULA",
           "Quando a Sorte": "Chico Chico", "Para Machucar Meu Coração": "João Gilberto",
           "Garota de Ipanema": "João Gilberto", "Rosa de Hiroshima": "Secos e Molhados"}
LETRA_ARQUIVO = {"Chega de Saudade": AQUI.parent / "karaoke/server/songs/chega-de-saudade-stan-getz/lyrics.txt"}


def _norm(p: str) -> str:
    import unicodedata
    p = unicodedata.normalize("NFD", p.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in p if unicodedata.category(c) != "Mn"))


def ler(xml: Path):
    """-> eventos por mão [(offset, dur, [midis], letra)], cifras [(offset, set(pcs))], bpm, armaduras."""
    from music21 import converter, harmony, key, note, chord, tempo
    sc = converter.parse(str(xml))
    partes = list(sc.parts)
    maos = []
    for p in partes[:2]:
        ev = []
        for el in p.flatten().notes:
            if isinstance(el, harmony.ChordSymbol):
                continue
            if el.tie is not None and el.tie.type in ("stop", "continue"):
                continue  # continuação de nota ligada não é ataque novo
            ps = [n.pitch.midi for n in el.notes] if isinstance(el, chord.Chord) else [el.pitch.midi]
            acid = [n.pitch.accidental is not None and n.pitch.accidental.displayStatus for n in
                    (el.notes if isinstance(el, chord.Chord) else [el])]
            txt = None
            if isinstance(el, note.Note) and el.lyrics:
                ly = el.lyrics[0]  # o MusicXML guarda o hífen à parte (syllabic), não no texto
                txt = {"begin": f"{ly.text}-", "middle": f"-{ly.text}-", "end": f"-{ly.text}"}.get(ly.syllabic, ly.text)
            ev.append((float(el.offset if el.activeSite is None else el.getOffsetInHierarchy(p)),
                       float(el.quarterLength), ps, txt, sum(bool(a) for a in acid)))
        maos.append(ev)
    cifras = []
    for cs in partes[0].flatten().getElementsByClass(harmony.ChordSymbol):
        cifras.append((float(cs.getOffsetInHierarchy(partes[0])), {p.pitchClass for p in cs.pitches}))
    mm = sc.flatten().getElementsByClass(tempo.MetronomeMark)
    bpm = float(mm[0].number) if mm else 100.0
    return maos, sorted(cifras, key=lambda c: c[0]), bpm


def palavras_da_partitura(md):
    """Junta sílabas ("tris-", "-te-", "-za") em palavras."""
    out, atual = [], ""
    for _, _, _, txt, _ in md:
        if not txt:
            continue
        for pedaco in txt.split(" "):
            atual += pedaco.strip("-")
            if not pedaco.endswith("-"):
                if _norm(atual):
                    out.append(_norm(atual))
                atual = ""
    return out


def cobertura_letra(md, oficial: str | None):
    if not oficial:
        return None
    ofi = [_norm(w) for w in re.findall(r"[\wÀ-ÿ']+", oficial)]
    ofi = [w for w in ofi if w]
    part = palavras_da_partitura(md)
    if not ofi:
        return None
    # alinha contra a letra repetida (gravação repete refrão): conta palavras da partitura que casam em ordem
    sm = difflib.SequenceMatcher(a=part, b=ofi * 3, autojunk=False)
    casadas = sum(b.size for b in sm.get_matching_blocks())
    unicas_ofi = len(ofi)
    return 100.0 * min(casadas, unicas_ofi * 3) / max(1, len(part)), 100.0 * min(1.0, casadas / unicas_ofi)


def metricas(maos, cifras, bpm, melodia_ref=None):
    md, me = (maos + [[], []])[:2]
    seg_por_tempo = 60.0 / bpm
    dur_total = max([o + d for o, d, *_ in md + me] or [1]) * seg_por_tempo

    def nps(ev):
        return sum(len(ps) for _, _, ps, *_ in ev) / dur_total

    todos = md + me
    por_ataque = defaultdict(list)
    for o, _, ps, *_ in todos:
        por_ataque[round(o, 3)] += ps
    acorde = float(np.mean([len(v) for v in por_ataque.values()])) if por_ataque else 0
    aberturas = [max(ps) - min(ps) for _, _, ps, *_ in todos if len(ps) > 1]
    abertura = 100.0 * np.mean([a > 12 for a in aberturas]) if aberturas else 0.0
    graves = [min(ps) for _, _, ps, *_ in me]
    saltos = float(np.mean(np.abs(np.diff(graves)))) if len(graves) > 1 else 0.0
    n_notas = sum(len(ps) for _, _, ps, *_ in todos)
    acid = 100.0 * sum(a for *_, a in todos) / max(1, n_notas)

    # coerência harmônica: nota pertence à cifra vigente?
    offs = [c[0] for c in cifras]
    dentro = total = 0
    for o, _, ps, *_ in todos:
        i = int(np.searchsorted(offs, o + 1e-6)) - 1
        if i < 0:
            continue
        pcs = cifras[i][1]
        for p in ps:
            total += 1
            dentro += (p % 12) in pcs
    harmonia = 100.0 * dentro / total if total else None

    melodia = None
    if melodia_ref:
        # por tempo inteiro: classe de altura da melodia cantada vs nota mais aguda da mão direita
        topo = {}
        for o, d, ps, *_ in md:
            for t in range(int(np.floor(o)), int(np.ceil(o + d))):
                topo[t] = max(ps) % 12
        bate = [topo.get(t) == pc for t, pc in melodia_ref.items()]
        melodia = 100.0 * np.mean(bate) if bate else None
    return {"md_nps": nps(md), "me_nps": nps(me), "acorde": acorde, "abertura": abertura,
            "saltos": saltos, "acid": acid, "harmonia": harmonia, "melodia": melodia}


def melodia_por_tempo(md):
    ref = {}
    for o, d, ps, *_ in md:
        for t in range(int(np.floor(o)), int(np.ceil(o + d))):
            ref.setdefault(t, max(ps) % 12)
    return ref


def main():
    from letra import buscar_letra
    linhas = []
    for pasta in sorted(p for p in SAIDA.iterdir() if p.is_dir()):
        nome = pasta.name
        if nome in LETRA_ARQUIVO and LETRA_ARQUIVO[nome].exists():
            oficial = LETRA_ARQUIVO[nome].read_text(encoding="utf-8")
        else:
            oficial = buscar_letra(nome, ARTISTA.get(nome) or "")
        for nivel in NIVEIS:
            ref = None
            base = pasta / "editaveis" / f"Acordes - {nivel}.musicxml"
            if base.exists():
                m_ac, _, _ = ler(base)
                ref = melodia_por_tempo(m_ac[0])
            for versao in VERSOES:
                xml = pasta / "editaveis" / f"{versao} - {nivel}.musicxml"
                if not xml.exists():
                    continue
                maos, cifras, bpm = ler(xml)
                usa_ref = versao in ("Pop2Piano", "AMT-APC")
                m = metricas(maos, cifras, bpm, ref if usa_ref else None)
                cob = cobertura_letra(maos[0], oficial) if versao in ("Acordes", "Hibrido", "HibridoAMT") else None
                m["letra"] = cob[1] if cob else None
                m.update(musica=nome, versao=versao, nivel=nivel)
                linhas.append(m)
                print(f"{nome[:22]:22s} {nivel:7s} {versao:10s} " + "  ".join(
                    f"{k}={'-' if m[k] is None else round(m[k], 1)}" for k in
                    ("letra", "md_nps", "me_nps", "acorde", "abertura", "saltos", "acid", "harmonia", "melodia")))
    (SAIDA / "analise.json").write_text(json.dumps(linhas, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== médias por nível × versão (7 músicas) ===")
    chaves = ("letra", "md_nps", "me_nps", "acorde", "abertura", "saltos", "acid", "harmonia", "melodia")
    print(f"{'nível':8s}{'versão':11s}" + "".join(f"{k:>10s}" for k in chaves))
    for nivel in NIVEIS:
        for versao in VERSOES:
            sel = [l for l in linhas if l["nivel"] == nivel and l["versao"] == versao]
            if not sel:
                continue
            vals = []
            for k in chaves:
                xs = [l[k] for l in sel if l[k] is not None]
                vals.append(f"{np.mean(xs):10.1f}" if xs else f"{'-':>10s}")
            print(f"{nivel:8s}{versao:11s}" + "".join(vals))
        print()


if __name__ == "__main__":
    main()
