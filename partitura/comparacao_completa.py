"""Página às cegas com a MÚSICA INTEIRA: prévia completa + partitura completa (PDF) de cada lado.

    python comparacao_completa.py <saida> rotulo1=biblioteca1 rotulo2=biblioteca2 [...] [--niveis Facil,Medio]
                                  [--versoes Facil=Acordes,Medio=HibridoAMT] [--musicas "A,B"]

Mesma página da comparacao_cega.py (notas 1-5, "melhor", revelar, copiar resultado), mas cada
opção é a prévia inteira e o PDF inteiro, com nomes neutros (A.mp3/A.pdf) pra não denunciar o
lado. Os arquivos entram como hardlink (sem copiar centenas de MB). A gravação original fica
acima das opções, como referência. Sem LLM.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from pathlib import Path

from comparacao_cega import MODELO, PADRAO

_TROCAS = [
    ('</style>', 'a{color:var(--ac)}</style>'),
    ('<div class="folha"><img src="${o.cego}?v=${VER}" alt=""></div>',
     '<p><a href="${o.pdf}" target="_blank" rel="noopener">abrir a partitura inteira (PDF)</a></p>'),
    ('<div class="folha"><img loading="lazy" src="${o.svg}?v=${VER}" alt=""></div>', ''),
    ('<p class="sub">${esc(c.ouvir)}</p>',
     '<p class="sub">${esc(c.ouvir)}</p>${c.original ? `<p class="sub">Gravação original: '
     '<audio controls preload="none" src="${c.original}"></audio></p>` : ""}'),
    ('<p class="sub">Ouça e leia às cegas, dê nota de 1 a 5 e marque a melhor. Depois revele.</p>',
     '<p class="sub">Música inteira: ouça cada opção do começo ao fim (e abra a partitura), dê nota '
     'de 1 a 5 e marque a melhor. Depois revele.</p>'),
]


def _modelo():
    m = MODELO
    for a, b in _TROCAS:
        assert a in m, a
        m = m.replace(a, b)
    return m


def _ligar(origem: Path, destino: Path):
    try:
        os.link(origem, destino)
    except OSError:
        shutil.copyfile(origem, destino)


def montar(lados: dict, saida: Path, niveis=("Facil", "Medio", "Dificil"), versoes=None, musicas=None,
           semente=7319, ouvir=None):
    versoes = {**PADRAO, **(versoes or {})}
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    rnd = random.Random(semente)
    rotulos = list(lados)
    # "pasta|Versao": esse lado usa outra versão (ex.: HibridoAMT × HibridoGravado da mesma biblioteca)
    versao_lado = {r: (str(lados[r]).split("|", 1) + [None])[1] for r in rotulos}
    lados = {r: str(lados[r]).split("|", 1)[0] for r in rotulos}
    ref = Path(lados[rotulos[0]])
    casos, sem = [], []
    for pasta_ref in sorted(p for p in ref.iterdir() if p.is_dir() and not p.name.startswith("pagina")):
        musica = pasta_ref.name
        if musicas and musica not in musicas:
            continue
        for nivel in niveis:
            vn = f"{versoes[nivel]} - {nivel}"
            vns = {r: f"{versao_lado[r]} - {nivel}" if versao_lado[r] else vn for r in rotulos}
            arqs = {r: (Path(lados[r]) / musica / f"{vns[r]} - previa.mp3", Path(lados[r]) / musica / f"{vns[r]}.pdf")
                    for r in rotulos}
            if not all(m.exists() and p.exists() for m, p in arqs.values()):
                sem.append(f"{musica} · {vn} (falta arquivo)")
                continue
            pasta = saida / f"{len(casos):02d}"
            pasta.mkdir()
            original = next((Path(lados[r]) / musica / "Original.mp3" for r in rotulos
                             if (Path(lados[r]) / musica / "Original.mp3").exists()), None)
            if original:
                _ligar(original, pasta / "original.mp3")
            ordem = rotulos[:]
            rnd.shuffle(ordem)
            opcoes = []
            for letra, r in zip("ABCDEFGHIJ", ordem):
                mp3, pdf = arqs[r]
                _ligar(mp3, pasta / f"{letra}.mp3")
                _ligar(pdf, pasta / f"{letra}.pdf")
                opcoes.append(dict(id=r, rotulo=r, letra=letra, mp3=f"{pasta.name}/{letra}.mp3",
                                   pdf=f"{pasta.name}/{letra}.pdf", svg="", cego="", medidas={}, correcoes=[]))
            ident = f"{musica} · {nivel}" if any(versao_lado.values()) else f"{musica} · {vn}"
            casos.append(dict(id=ident, titulo=ident, musica=musica, versao=vn,
                              ouvir=ouvir or "Música inteira, as opções na mesma versão e nível.",
                              original=f"{pasta.name}/original.mp3" if original else "",
                              opcoes=opcoes, diferem=[], pares=[], so_dedos=None))
            print("[completa]", ident, flush=True)
    dados = dict(casos=casos, descartados=[dict(id=x, titulo=x) for x in sem])
    (saida / "casos.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    (saida / "index.html").write_text(_modelo().replace("__CASOS__", json.dumps(dados, ensure_ascii=False)),
                                      encoding="utf-8")
    return saida / "index.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("saida", type=Path)
    ap.add_argument("lados", nargs="+", help="rotulo=pasta_da_biblioteca[|Versao] (o 1º é a referência)")
    ap.add_argument("--niveis", default="Facil,Medio,Dificil")
    ap.add_argument("--versoes", default="", help="ex.: Medio=Acordes,Dificil=Acordes")
    ap.add_argument("--musicas", default="")
    ap.add_argument("--ouvir", default=None)
    a = ap.parse_args()
    lados = dict(x.split("=", 1) for x in a.lados)
    versoes = dict(x.split("=", 1) for x in a.versoes.split(",") if x)
    musicas = set(a.musicas.split(",")) if a.musicas else None
    print(montar(lados, a.saida, a.niveis.split(","), versoes, musicas, ouvir=a.ouvir))


if __name__ == "__main__":
    main()
