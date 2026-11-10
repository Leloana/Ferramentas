"""Mede a tocabilidade de partituras já geradas (MusicXML), sem regenerar nada.

    python avaliar_maos.py saida                  # todas as partituras da biblioteca
    python avaliar_maos.py exemplos --json r.json # qualquer pasta ou arquivo .musicxml

Para cada partitura: trechos que a mão não alcança antes da correção, quantos a
correção resolve, quantos sobram (e quantos desses são da melodia cantada, que não
muda) e mudanças de posição por minuto. Notas com letra contam como melodia protegida.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from maos import tornar_tocavel


def eventos_da_partitura(xml: Path):
    from music21 import converter, harmony, tempo
    sc = converter.parse(str(xml))
    partes = list(sc.parts)
    bpm = 120.0
    mm = sc.recurse().getElementsByClass(tempo.MetronomeMark).first()
    if mm is not None and mm.number:
        bpm = float(mm.number)
    maos, protegidas = [], set()
    for parte in partes[:2]:
        ev = []
        for el in parte.stripTies().flatten().notes:
            if isinstance(el, harmony.ChordSymbol):
                continue  # cifra
            ps = sorted({p.midi for p in el.pitches})
            off = float(el.offset)
            ev.append((off, float(el.quarterLength), ps))
            if el.lyrics:
                protegidas |= {(round(off, 6), p) for p in ps}
        maos.append(sorted(ev, key=lambda e: e[0]))
    while len(maos) < 2:
        maos.append([])
    return maos[0], maos[1], bpm, protegidas


def nivel_do_nome(nome: str) -> str:
    n = nome.lower()
    return "facil" if "facil" in n else "dificil" if "dificil" in n else "medio"


def avaliar(xml: Path):
    md, me, bpm, prot = eventos_da_partitura(xml)
    nivel = nivel_do_nome(xml.stem)
    _, _, _, _, antes = tornar_tocavel(md, me, nivel, bpm, prot, corrigir=False)
    _, _, _, _, depois = tornar_tocavel(md, me, nivel, bpm, prot, corrigir=True)
    fim = max([o + d for o, d, _ in md + me] or [0])
    minutos = max(fim * 60 / bpm / 60, 1e-6)
    return dict(
        arquivo=str(xml), nivel=nivel, bpm=round(bpm, 1),
        dificeis_antes=antes["resumo"]["restantes"],
        tipos_antes=dict(Counter(p["tipo"] for p in antes["restantes"])),
        correcoes=depois["resumo"]["corrigidos"],
        acoes=dict(Counter(c["acao"].split(" ")[0] + " " + c["acao"].split(" ")[1] for c in depois["correcoes"])),
        dificeis_depois=depois["resumo"]["restantes"],
        dificeis_depois_na_melodia=depois["resumo"]["restantes_na_melodia"],
        mudancas_por_min={k: round(v / minutos, 1) for k, v in depois["mudancas_de_posicao"].items()},
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("alvo", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    arquivos = [a.alvo] if a.alvo.is_file() else sorted(a.alvo.rglob("*.musicxml"))
    resultados = []
    for x in arquivos:
        try:
            r = avaliar(x)
        except Exception as e:  # partitura quebrada não derruba o relatório
            print(f"[erro] {x}: {e}", file=sys.stderr)
            continue
        resultados.append(r)
        print(f"{x}: difíceis {r['dificeis_antes']} -> {r['dificeis_depois']} "
              f"(melodia {r['dificeis_depois_na_melodia']}), {r['correcoes']} correções, "
              f"mudanças/min {r['mudancas_por_min']}")
    if a.json:
        a.json.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
