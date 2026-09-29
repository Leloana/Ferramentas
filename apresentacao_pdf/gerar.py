#!/usr/bin/env python3
"""
Apresentação em PDF com cara de Canva, a partir de um arquivo .toml simples.

    python3 gerar.py novo minha_apresentacao      # cria a pasta com um modelo pronto
    python3 gerar.py minha_apresentacao/slides.toml   # gera slides.pdf ao lado

Sem dependências (Python 3.11+). Precisa do Google Chrome, Chromium ou Edge instalado.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import webbrowser
from pathlib import Path

AQUI = Path(__file__).resolve().parent

TEMA_PADRAO = {
    "cor": "#2450d8",  # cor principal (capa, destaques)
    "fundo": "#f7f6f2",  # fundo das páginas
    "texto": "#1c1c1e",
    "bom": "#1d8248",  # verde: sobe, pode, ✓
    "ruim": "#c7372f",  # vermelho: cai, não pode, ✕
    "extra": "#c27a00",  # terceira cor dos blocos
    "fonte": "Barlow",
    "fonte_titulo": "Barlow Condensed",
    "logo": "",
}


# ---------- texto ----------

def t(s: object) -> str:
    """Escapa HTML e aplica *destaque* (cor principal) e **negrito**."""
    s = html.escape(str(s or ""))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    return s.replace("\n", "<br>")


class Ctx:
    def __init__(self, base: Path):
        self.base = base

    def img(self, nome: str | None, classe: str = "") -> str:
        if not nome:
            return ""
        p = (self.base / nome).resolve()
        if not p.exists():
            print(f"aviso: imagem não encontrada: {p}", file=sys.stderr)
            return ""
        return f'<img class="{classe}" src="{p.as_uri()}" alt="">'


# ---------- layouts ----------

def capa(s, c: Ctx, tema):
    logo = c.img(tema.get("logo"), "logo") if tema.get("logo") else ""
    selo = f'<span class="pill vidro">{t(s.get("selo"))}</span>' if s.get("selo") else ""
    arte = f'<div class="moldura">{c.img(s.get("imagem"))}</div>' if s.get("imagem") else ""
    so_texto = "" if arte else " so-texto"
    return f"""<section class="page capa{so_texto}">
  <div>{logo}<h1 class="display">{t(s.get("titulo"))}</h1>
  <p class="tag">{t(s.get("subtitulo"))}</p>{selo}</div>{arte}</section>"""


def cards(s, c: Ctx, tema):
    itens = "".join(
        f'<div class="card">{c.img(i.get("icone"))}<h3>{t(i.get("titulo"))}</h3><p>{t(i.get("texto"))}</p></div>'
        for i in s.get("cards", [])
    )
    n = max(len(s.get("cards", [])), 1)
    selo = f'<span class="pill ok topo">{t(s.get("selo"))}</span>' if s.get("selo") else ""
    return f"""<section class="page">{selo}{cab(s)}
  <div class="grade" style="grid-template-columns:repeat({n},1fr)">{itens}</div></section>"""


def comparacao(s, c: Ctx, tema):
    def col(lado, classe):
        itens = "".join(f"<li>{t(i)}</li>" for i in lado.get("itens", []))
        return f'<div class="col {classe}"><h3>{t(lado.get("titulo"))}</h3><ul>{itens}</ul></div>'
    return f"""<section class="page">{cab(s)}
  <div class="vs">{col(s.get("antes", {}), "antes")}{col(s.get("depois", {}), "depois")}</div></section>"""


def frase(s, c: Ctx, tema):
    chips = "".join(f'<span class="pill borda">{t(x)}</span>' for x in s.get("chips", []))
    cores = "".join(f'<i style="background:{html.escape(x)}"></i>' for x in s.get("cores", []))
    paleta = f'<div class="paleta">{cores}<small>{t(s.get("legenda_cores"))}</small></div>' if cores else ""
    lado = ""
    if s.get("celular"):
        cel = s["celular"]
        linhas = "".join(
            f'<div class="linha">{t(l.get("texto"))}<b class="{"sobe" if l.get("sobe", True) else "cai"}">'
            f'{"▲" if l.get("sobe", True) else "▼"} {t(l.get("valor"))}</b></div>'
            for l in cel.get("linhas", [])
        )
        botao = f'<div class="botao">{t(cel.get("botao"))}</div>' if cel.get("botao") else ""
        lado = f"""<div class="celular"><div class="tela"><p class="rotulo">{t(cel.get("rotulo"))}</p>
  <h4>{t(cel.get("titulo"))}</h4>{linhas}{botao}</div></div>"""
    elif s.get("imagem"):
        lado = f'<div class="moldura clara">{c.img(s.get("imagem"))}</div>'
    return f"""<section class="page duas">
  <div><p class="rotulo">{t(s.get("rotulo"))}</p><blockquote class="display">{t(s.get("frase"))}</blockquote>
  <p class="sub">{t(s.get("sub"))}</p><div class="chips">{chips}</div>{paleta}</div>{lado}</section>"""


def blocos(s, c: Ctx, tema):
    etq = "".join(
        f'<span class="pill {"ok" if e.get("bom", True) else "nao"}">{"✓" if e.get("bom", True) else "✕"} {t(e.get("texto"))}</span>'
        for e in s.get("etiquetas", [])
    )
    estilos = ["cheio", "suave", "borda"]
    bl = "".join(
        f'<div class="bloco {b.get("estilo", estilos[i % 3])}"><h3>{t(b.get("titulo"))}</h3><p>{t(b.get("texto"))}</p></div>'
        for i, b in enumerate(s.get("blocos", []))
    )
    nums = "".join(f'<div class="ref"><b>{t(n.get("valor"))}</b><span>{t(n.get("texto"))}</span></div>' for n in s.get("numeros", []))
    n = max(len(s.get("blocos", [])), 1)
    return f"""<section class="page">{cab(s)}<div class="etiquetas">{etq}</div>
  <div class="blocos" style="grid-template-columns:1.3fr{' 1fr' * (n - 1)}">{bl}</div>
  <div class="refs">{nums}</div></section>"""


def numero(s, c: Ctx, tema):
    itens = "".join(f'<div><span>{t(i.get("nome"))}</span><b>{t(i.get("valor"))}</b></div>' for i in s.get("itens", []))
    lado = s.get("lado", {})
    barras = "".join(
        f'<div class="barra"><div class="lbl"><span>{t(b.get("nome"))}</span><b>{t(b.get("valor"))}</b></div>'
        f'<div class="trilho"><div class="enche" style="width:{max(2, min(100, float(b.get("pct", 50))))}%"></div></div></div>'
        for b in lado.get("barras", [])
    )
    faixa = ""
    if s.get("faixa"):
        f = s["faixa"]
        faixa = f'<div class="faixa">{c.img(f.get("icone"))}<span>{t(f.get("texto"))}</span></div>'
    return f"""<section class="page duas numero">
  <div><p class="rotulo">{t(s.get("rotulo"))}</p><div class="grande">{t(s.get("valor"))}<small>{t(s.get("unidade"))}</small></div>
  <div class="itens">{itens}</div></div>
  <div><p class="rotulo">{t(lado.get("rotulo"))}</p><h3 class="subtitulo">{t(lado.get("titulo"))}</h3>{barras}
  <p class="nota">{t(lado.get("nota"))}</p></div>{faixa}</section>"""


def decisoes(s, c: Ctx, tema):
    itens = "".join(
        f'<div class="d"><h3>{t(i.get("tema"))}</h3><p class="sug">{t(i.get("sugestao"))}</p>'
        f'<div class="alts">{"".join(f"<span>{t(a)}</span>" for a in i.get("alternativas", []))}</div></div>'
        for i in s.get("itens", [])
    )
    return f"""<section class="page">{cab(s)}<p class="lead">{t(s.get("sub"))}</p>
  <div class="dgrid">{itens}</div></section>"""


def cab(s) -> str:
    return f'<p class="rotulo">{t(s.get("rotulo"))}</p><h2 class="display">{t(s.get("titulo"))}</h2>'


LAYOUTS = {
    "capa": capa,
    "cards": cards,
    "comparacao": comparacao,
    "frase": frase,
    "blocos": blocos,
    "numero": numero,
    "decisoes": decisoes,
}


# ---------- estilo ----------

def css(tema) -> str:
    return (AQUI / "estilo.css").read_text(encoding="utf-8").replace(
        "/*TEMA*/",
        f"""--cor:{tema['cor']};--fundo:{tema['fundo']};--texto:{tema['texto']};
  --bom:{tema['bom']};--ruim:{tema['ruim']};--extra:{tema['extra']};
  --fonte:"{tema['fonte']}";--fonte-titulo:"{tema['fonte_titulo']}";""",
    )


def montar_html(dados: dict, base: Path) -> str:
    tema = {**TEMA_PADRAO, **dados.get("tema", {})}
    c = Ctx(base)
    paginas = []
    slides = dados.get("slide", [])
    if not slides:
        sys.exit("nenhum [[slide]] no arquivo")
    for n, s in enumerate(slides, 1):
        layout = s.get("layout", "cards")
        if layout not in LAYOUTS:
            sys.exit(f"slide {n}: layout '{layout}' não existe. Use um de: {', '.join(LAYOUTS)}")
        pg = LAYOUTS[layout](s, c, tema)
        extra = ""
        if s.get("rodape"):
            extra += f'<span class="rodape">{t(s["rodape"])}</span>'
        if layout != "capa":
            extra += f'<span class="num">{n:02d}</span>'
        paginas.append(pg.replace("</section>", extra + "</section>", 1))
    fontes = "|".join(
        f"family={f.replace(' ', '+')}:wght@400;500;600;700;800" for f in {tema["fonte"], tema["fonte_titulo"]}
    )
    titulo = html.escape(dados.get("titulo") or slides[0].get("titulo") or "Apresentação")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title>
<link href="https://fonts.googleapis.com/css2?{fontes.replace('|', '&')}&display=swap" rel="stylesheet">
<style>{css(tema)}</style></head><body>
{chr(10).join(paginas)}
</body></html>"""


# ---------- PDF ----------

def achar_chrome() -> str:
    nomes = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "chrome"]
    for n in nomes:
        if p := shutil.which(n):
            return p
    fixos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for p in fixos:
        if os.path.exists(p):
            return p
    sys.exit("Chrome, Chromium ou Edge não encontrado. Instale um deles.")


def gerar(arquivo: Path, saida: Path | None, manter_html: bool, abrir: bool) -> Path:
    dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    pdf = (saida or arquivo.with_suffix(".pdf")).resolve()
    conteudo = montar_html(dados, arquivo.parent)
    if manter_html:
        html_path = pdf.with_suffix(".html")
        html_path.write_text(conteudo, encoding="utf-8")
    else:
        fd, nome = tempfile.mkstemp(suffix=".html")
        os.close(fd)
        html_path = Path(nome)
        html_path.write_text(conteudo, encoding="utf-8")
    cmd = [
        achar_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--virtual-time-budget=8000", f"--print-to-pdf={pdf}", html_path.as_uri(),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not manter_html:
        html_path.unlink(missing_ok=True)
    if not pdf.exists():
        sys.exit(f"o Chrome não gerou o PDF:\n{r.stderr[-800:]}")
    print(pdf)
    if abrir:
        webbrowser.open(pdf.as_uri())
    return pdf


def novo(pasta: Path) -> None:
    if pasta.exists() and any(pasta.iterdir()):
        sys.exit(f"{pasta} já existe e não está vazia")
    shutil.copytree(AQUI / "modelo", pasta, dirs_exist_ok=True)
    print(f"criado: {pasta / 'slides.toml'}\nedite e rode: python3 {Path(__file__).name} {pasta / 'slides.toml'}")


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "novo":
        if len(sys.argv) != 3:
            sys.exit("uso: python3 gerar.py novo <pasta>")
        return novo(Path(sys.argv[2]))
    ap = argparse.ArgumentParser(description="Gera apresentação em PDF a partir de um .toml")
    ap.add_argument("arquivo", type=Path, help="arquivo .toml com os slides")
    ap.add_argument("-o", "--saida", type=Path, help="PDF de saída (padrão: ao lado do .toml)")
    ap.add_argument("--html", action="store_true", help="guarda também o .html (pra ajustar à mão)")
    ap.add_argument("--abrir", action="store_true", help="abre o PDF ao terminar")
    a = ap.parse_args()
    if not a.arquivo.exists():
        sys.exit(f"não achei {a.arquivo}")
    gerar(a.arquivo, a.saida, a.html, a.abrir)


if __name__ == "__main__":
    main()
