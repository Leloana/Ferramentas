"""Regressão de legibilidade e tocabilidade das partituras prontas, sem ouvir nada (sem LLM).

    python regressao.py saida --salvar base.json            # mede e guarda a referência
    python regressao.py saida --base base.json              # mede e acusa o que piorou
    python regressao.py saida --musicas "Ode,Calice" --versao AMT-APC

Por partitura (MusicXML em <música>/editaveis/<Versão> - <Nível>.musicxml):
- linhas suplementares na clave de sol, contando a 8va como o Verovio desenha (uma oitava abaixo);
- notas embaixo da pauta dentro da 8va (devem ser 0) e linhas 8va;
- acidentes escritos;
- trechos que a mão não alcança e mudanças de posição por minuto (modelo do maos.py);
- síncopes que atravessam o tempo (tocavel.py);
- compassos iguais a algum anterior (repetição escrita igual);
- números de dedo desenhados um em cima do outro (renderiza com o Verovio, como no PDF);
- ordem dos níveis: notas por segundo da direita fácil < médio < difícil.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NIVEIS = ("Facil", "Medio", "Dificil")
# métrica -> quanto pode piorar sem acusar (absoluto); maior = pior em todas
TOLERANCIA = dict(suplementares=5, embaixo_na_8va=0, linhas_8va=2, acidentes=10, dificeis=1,
                  mudancas_por_min=3.0, sincopes=5, dedos_sobrepostos=0)
MELHOR_MAIOR = {"compassos_repetidos"}   # aqui maior é melhor


def _suplementares(dn):
    import gerar
    return gerar._suplementares(dn)


def leitura(xml: Path) -> dict:
    """Linhas suplementares (com a 8va), notas embaixo da pauta na 8va, linhas 8va, acidentes."""
    from music21 import converter
    sc = converter.parse(str(xml))
    d = sc.parts[0]
    texto = xml.read_text(encoding="utf-8")
    linhas = len(re.findall(r'<octave-shift[^>]*type="down"', texto))
    from music21 import spanner
    faixas = []   # (início, fim) de cada 8va; na importação o spanner cobre as notas entre as pontas
    for sp in d.recurse().getElementsByClass(spanner.Ottava):
        els = sp.getSpannedElements()
        if els:
            faixas.append((float(els[0].getOffsetInHierarchy(d)), float(els[-1].getOffsetInHierarchy(d))))
    sup = embaixo8 = 0
    for n in d.recurse().notes:
        o = float(n.getOffsetInHierarchy(d))
        dentro = any(a <= o <= b for a, b in faixas)
        for p in n.pitches:
            dn = p.diatonicNoteNum - 7 * dentro
            s = _suplementares(dn)
            sup += s
            if dentro and dn <= 29:
                embaixo8 += 1
    return dict(suplementares=sup, embaixo_na_8va=embaixo8, linhas_8va=linhas,
                acidentes=len(re.findall(r"<accidental", texto)))


def repetidos(md, me) -> int:
    c = {}
    for mao, ev in (("d", md), ("e", me)):
        for o, d, ps in ev:
            k = int(o // 4)
            c.setdefault(k, []).append((mao, round(o - 4 * k, 3), round(d, 3), tuple(ps)))
    vistos, n = set(), 0
    for k in sorted(c):
        t = tuple(sorted(c[k]))
        n += t in vistos
        vistos.add(t)
    return n


_RE_FING = re.compile(r'class="fing"[^>]*>\s*<text x="(-?[\d.]+)" y="(-?[\d.]+)" text-anchor="(\w+)"(.*?)</text>', re.S)


def dedos_sobrepostos(xml: Path) -> int:
    import verovio
    import gerar
    verovio.enableLog(False)
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 42, "pageMarginTop": 80,
                   "pageMarginBottom": 80, "pageMarginLeft": 80, "pageMarginRight": 80,
                   "adjustPageHeight": False, "footer": "none", "breaks": "auto", **gerar.OPCOES_DEDOS})
    tk.loadData(gerar.xml_para_verovio(xml.read_text(encoding="utf-8")))
    total = 0
    for i in range(1, tk.getPageCount() + 1):
        svg = gerar.dedos_ao_lado(gerar._desembaralhar(tk.renderToSVG(i)))
        caixas = []
        for m in _RE_FING.finditer(svg):
            x, y, anc = float(m.group(1)), float(m.group(2)), m.group(3)
            w = 150 * max(1, len(re.findall(r">\s*(\d)\s*<", m.group(4))))
            a = x - w if anc == "end" else (x if anc == "start" else x - w / 2)
            caixas.append((a, a + w, y))
        caixas.sort()
        for j, c in enumerate(caixas):
            for k in caixas[j + 1:]:
                if k[0] >= c[1]:
                    break
                if abs(c[2] - k[2]) < 150:
                    total += 1
    return total


def medir_partitura(xml: Path, nivel: str) -> dict:
    from avaliar_maos import eventos_da_partitura
    from tocavel import medir
    md, me, bpm, _ = eventos_da_partitura(xml)
    t = medir(md, me, bpm, nivel.lower())
    fim = max([o + d for o, d, _ in md + me] or [1])
    r = dict(leitura(xml), dificeis=t["dificeis"],
             mudancas_por_min=round(t["direita"]["mudancas_por_min"] + t["esquerda"]["mudancas_por_min"], 1),
             sincopes=t["direita"]["sincopes"] + t["esquerda"]["sincopes"],
             compassos_repetidos=repetidos(md, me), dedos_sobrepostos=dedos_sobrepostos(xml),
             notas_por_s_direita=round(sum(len(ps) for _, _, ps in md) / (fim * 60 / bpm), 2))
    return r


def medir_biblioteca(saida: Path, musicas=None, versao="AMT-APC") -> dict:
    res = {}
    for pasta in sorted(p for p in saida.iterdir() if (p / "editaveis").is_dir()):
        if musicas and pasta.name not in musicas:
            continue
        por_nivel = {}
        for nivel in NIVEIS:
            xml = pasta / "editaveis" / f"{versao} - {nivel}.musicxml"
            if xml.exists():
                por_nivel[nivel] = medir_partitura(xml, nivel)
        if por_nivel:
            ordem = [por_nivel[n]["notas_por_s_direita"] for n in NIVEIS if n in por_nivel]
            por_nivel["ordem_ok"] = all(a <= b + 1e-9 for a, b in zip(ordem, ordem[1:]))
            res[pasta.name] = por_nivel
    return res


def comparar(atual: dict, base: dict) -> list[str]:
    pioras = []
    for musica, niveis in atual.items():
        for nivel, m in niveis.items():
            if nivel == "ordem_ok":
                if base.get(musica, {}).get("ordem_ok", True) and not m:
                    pioras.append(f"{musica}: níveis fora de ordem de dificuldade")
                continue
            b = base.get(musica, {}).get(nivel)
            if not b:
                continue
            for k, v in m.items():
                if k not in b or k == "notas_por_s_direita":
                    continue
                if k in MELHOR_MAIOR:
                    if v < b[k]:
                        pioras.append(f"{musica} {nivel}: {k} {b[k]} → {v}")
                elif v > b[k] + TOLERANCIA.get(k, 0):
                    pioras.append(f"{musica} {nivel}: {k} {b[k]} → {v}")
    return pioras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("saida", type=Path)
    ap.add_argument("--musicas", default="")
    ap.add_argument("--versao", default="AMT-APC")
    ap.add_argument("--salvar", type=Path)
    ap.add_argument("--base", type=Path)
    a = ap.parse_args()
    musicas = {m.strip() for m in a.musicas.split(",") if m.strip()} or None
    atual = medir_biblioteca(a.saida, musicas, a.versao)
    for musica, niveis in atual.items():
        for nivel in NIVEIS:
            if nivel in niveis:
                m = niveis[nivel]
                print(f"{musica[:18]:18s} {nivel:7s} sup {m['suplementares']:4d} 8va {m['linhas_8va']:2d} "
                      f"emb8va {m['embaixo_na_8va']} acid {m['acidentes']:4d} dif {m['dificeis']:2d} "
                      f"mud/min {m['mudancas_por_min']:5.1f} sinc {m['sincopes']:4d} rep {m['compassos_repetidos']:3d} "
                      f"dedos× {m['dedos_sobrepostos']}")
        if not niveis.get("ordem_ok", True):
            print(f"{musica[:18]:18s} ATENÇÃO: níveis fora de ordem de dificuldade")
    if a.salvar:
        a.salvar.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"referência salva em {a.salvar}")
    if a.base:
        pioras = comparar(atual, json.loads(a.base.read_text(encoding="utf-8")))
        print("\n".join(["PIOROU:"] + pioras) if pioras else "nada piorou em relação à referência")
        sys.exit(1 if pioras else 0)


if __name__ == "__main__":
    main()
