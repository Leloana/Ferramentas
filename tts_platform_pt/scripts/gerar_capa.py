"""Gera a imagem de capa (thumbnail) de um vídeo: gera uma cena NOVA e
chamativa via ComfyUI (mesmo workflow Krea2 de `gerar_imagens.py`, a partir
de um `--prompt` escrito à mão) e desenha o título por cima como texto real
— não pede pro modelo de difusão gerar o texto na imagem, porque esse é
justamente o bug conhecido do Krea2/ComfyUI usado aqui (texto
borrado/ilegível, ver `comfy/GOTCHAS.md` e `_REGRA_SEM_TEXTO` em
`gerar_imagens.py`). O texto é desenhado com Pillow (já é dependência
transitiva do projeto, via coqui-tts).

**A capa não deve reaproveitar nenhuma das imagens do corpo do vídeo**: o
objetivo é fazer quem estiver rolando o feed parar e clicar, o que pede uma
cena mais chamativa/dramática do que as imagens narrativas de cada frase
(essas são pensadas pra ilustrar o que está sendo narrado naquele momento,
não pra vender o vídeo). Por isso `--prompt` é obrigatório (a menos que
`--imagem` aponte pra um fundo já pronto): escreva a cena em inglês, do
jeito mais visualmente impactante que fizer sentido pro tema do vídeo,
mesma lógica de `texto_prompts.json` em `gerar_imagens.py`.

Uso:
    python scripts/gerar_capa.py Projetos/Video_1/historia_humanidade_parte2/texto_manifesto.json --prompt "dramatic close-up of ancient Roman ruins at golden hour, cinematic lighting"
    # sem --titulo, usa a 1a linha de descricao.md (sem o "👇" final)
    python scripts/gerar_capa.py Projetos/Video_1/historia_humanidade_parte2/texto_manifesto.json --prompt "..." --titulo "História da Humanidade — Parte 2/5"
    # reaproveitando um fundo de capa já gerado antes (só reajusta o título, não chama o ComfyUI de novo)
    python scripts/gerar_capa.py Projetos/Video_1/historia_humanidade_parte2/texto_manifesto.json --imagem Projetos/Video_1/historia_humanidade_parte2/capa_fundo.png

Saída: <projeto>/capa.png (título desenhado) + <projeto>/capa_fundo.png (cena
gerada, sem texto, reaproveitável se só o título mudar) + <projeto>/capa_manifesto.json
(prompt_final/arquivo_comfy, mesma lógica de rastreabilidade do
`<nome>_imagens_manifesto.json` — ver CLAUDE.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

from gerar_imagens import WORKFLOW_PADRAO, gerar_imagem

# O título vem de descricao.md e pode conter emoji (ver convenção do gancho em
# CLAUDE.md); o console do Windows usa cp1252 por padrão, que não codifica
# esses caracteres e derruba o script com UnicodeEncodeError num print()
# puramente informativo.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

_RESOLUCOES = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

# Mesma família (Arial) usada na legenda do vídeo (ver _FONTE_LEGENDA em
# montar_video.py) — bold aqui porque título de capa precisa de mais peso
# visual que legenda de vídeo curto.
_FONTES_CANDIDATAS = [
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
]

_MARGEM_LR = 90
_MARGEM_INFERIOR = 130
_ALTURA_MAX_TEXTO_FRAC = 0.38  # fração da altura do canvas reservada pro bloco de título
_TAMANHO_FONTE_INICIAL_FRAC = 0.10  # fração da largura do canvas
_TAMANHO_FONTE_MINIMO = 44
_PASSO_REDUCAO_FONTE = 4
_ESPACAMENTO_LINHA = 1.18
_STROKE_WIDTH = 6

# Escurece a parte de baixo da imagem em gradiente (0 = topo do escurecimento,
# 1 = base do canvas) pra o título ficar legível em cima de qualquer fundo,
# sem depender só do contorno preto do texto.
_Y_INICIO_ESCURECIMENTO_FRAC = 0.42
_OPACIDADE_MAX_ESCURECIMENTO = 0.80


def _fonte_disponivel() -> Path:
    for caminho in _FONTES_CANDIDATAS:
        if caminho.exists():
            return caminho
    raise SystemExit(
        "Nenhuma fonte Arial encontrada em C:\\Windows\\Fonts — "
        "ajuste _FONTES_CANDIDATAS em gerar_capa.py pro seu sistema."
    )


def _cobrir_redimensionar(imagem: Image.Image, largura: int, altura: int) -> Image.Image:
    """Redimensiona + corta pra cobrir exatamente largura x altura (como
    `background-size: cover`), preservando a proporção original em vez de
    esticar — as imagens do ComfyUI não saem sempre no pixel exato do
    canvas final (ver nota de supersample em montar_video.py)."""
    razao_alvo = largura / altura
    razao_original = imagem.width / imagem.height
    if razao_original > razao_alvo:
        nova_altura = altura
        nova_largura = round(altura * razao_original)
    else:
        nova_largura = largura
        nova_altura = round(largura / razao_original)
    imagem = imagem.resize((nova_largura, nova_altura), Image.LANCZOS)
    x = (nova_largura - largura) // 2
    y = (nova_altura - altura) // 2
    return imagem.crop((x, y, x + largura, y + altura))


def _aplicar_escurecimento(imagem: Image.Image) -> Image.Image:
    largura, altura = imagem.size
    y_inicio = int(altura * _Y_INICIO_ESCURECIMENTO_FRAC)
    col = np.zeros(altura, dtype=np.uint8)
    ys = np.arange(y_inicio, altura)
    if len(ys) > 0:
        t = (ys - y_inicio) / max(1, altura - y_inicio)
        col[y_inicio:] = (255 * _OPACIDADE_MAX_ESCURECIMENTO * t).astype(np.uint8)
    mascara = Image.fromarray(np.tile(col[:, None], (1, largura)), mode="L")
    preto = Image.new("RGB", (largura, altura), (0, 0, 0))
    resultado = imagem.convert("RGB").copy()
    resultado.paste(preto, (0, 0), mascara)
    return resultado


def _quebrar_linhas(draw: ImageDraw.ImageDraw, texto: str, fonte: ImageFont.FreeTypeFont, largura_max: int) -> list[str]:
    palavras = texto.split()
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        candidato = f"{atual} {palavra}".strip()
        if draw.textlength(candidato, font=fonte) <= largura_max or not atual:
            atual = candidato
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _ajustar_fonte_e_quebras(
    draw: ImageDraw.ImageDraw, texto: str, caminho_fonte: Path, largura_max: int, altura_max: int, tamanho_inicial: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Reduz o tamanho da fonte até o título (já quebrado em linhas) caber
    na largura e na altura reservadas — sem isso, um título longo estoura o
    bloco de texto ou fica ilegivelmente comprimido numa única linha."""
    tamanho = tamanho_inicial
    ultimo: tuple[ImageFont.FreeTypeFont, list[str]] | None = None
    while tamanho >= _TAMANHO_FONTE_MINIMO:
        fonte = ImageFont.truetype(str(caminho_fonte), tamanho)
        linhas = _quebrar_linhas(draw, texto, fonte, largura_max)
        altura_linha = (fonte.getbbox("Ág")[3] - fonte.getbbox("Ág")[1]) * _ESPACAMENTO_LINHA
        altura_total = altura_linha * len(linhas)
        maior_linha = max(draw.textlength(l, font=fonte) for l in linhas)
        ultimo = (fonte, linhas)
        if altura_total <= altura_max and maior_linha <= largura_max:
            return fonte, linhas
        tamanho -= _PASSO_REDUCAO_FONTE
    return ultimo


def gerar_capa(imagem_fundo: Path, titulo: str, destino: Path, proporcao: str = "9:16") -> Path:
    largura, altura = _RESOLUCOES[proporcao]
    base = Image.open(imagem_fundo)
    base = _cobrir_redimensionar(base, largura, altura)
    base = _aplicar_escurecimento(base)

    draw = ImageDraw.Draw(base)
    caminho_fonte = _fonte_disponivel()
    largura_max_texto = largura - 2 * _MARGEM_LR
    altura_max_texto = int(altura * _ALTURA_MAX_TEXTO_FRAC)
    tamanho_inicial = int(largura * _TAMANHO_FONTE_INICIAL_FRAC)

    fonte, linhas = _ajustar_fonte_e_quebras(
        draw, titulo, caminho_fonte, largura_max_texto, altura_max_texto, tamanho_inicial,
    )

    altura_linha = (fonte.getbbox("Ág")[3] - fonte.getbbox("Ág")[1]) * _ESPACAMENTO_LINHA
    altura_total = altura_linha * len(linhas)
    y = altura - _MARGEM_INFERIOR - altura_total
    for linha in linhas:
        largura_linha = draw.textlength(linha, font=fonte)
        x = (largura - largura_linha) / 2
        draw.text(
            (x, y), linha, font=fonte, fill="white",
            stroke_width=_STROKE_WIDTH, stroke_fill="black",
        )
        y += altura_linha

    destino.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(destino, "PNG")
    return destino


def _titulo_da_descricao(projeto: Path) -> str | None:
    descricao = projeto / "descricao.md"
    if not descricao.exists():
        return None
    primeira_linha = descricao.read_text(encoding="utf-8").splitlines()[0]
    return primeira_linha.replace("👇", "").strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifesto", type=Path, help="Caminho do <nome>_manifesto.json gerado por gerar_video.py")
    ap.add_argument("--titulo", default=None, help="Padrão: 1a linha de <projeto>/descricao.md, sem o 👇 final")
    ap.add_argument("--prompt", default=None, help=(
        "Descrição visual em inglês, escrita à mão, de uma cena NOVA e chamativa pra capa "
        "(não reaproveita as imagens do corpo do vídeo) — mesma lógica de texto_prompts.json "
        "em gerar_imagens.py, mas pensada pra fazer alguém parar de rolar e clicar, não pra "
        "ilustrar uma frase específica da narração. Obrigatório, a menos que --imagem seja "
        "passado."
    ))
    ap.add_argument("--imagem", type=Path, default=None, help=(
        "Usa esse fundo já pronto em vez de gerar um novo no ComfyUI (pula --prompt). Útil "
        "pra só reajustar o texto do título em cima de um capa_fundo.png gerado antes."
    ))
    ap.add_argument("--workflow", type=Path, default=None, help="Padrão: mesmo workflow de gerar_imagens.py")
    ap.add_argument("--aspect-ratio", default="9:16 (Portrait Widescreen)", help="Formato do ResolutionSelector do workflow (ComfyUI)")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--proporcao", choices=sorted(_RESOLUCOES), default="9:16", help="Resolução final da capa (canvas do Pillow)")
    ap.add_argument("--saida", type=Path, default=None)
    args = ap.parse_args()

    if not args.manifesto.exists():
        raise SystemExit(f"Manifesto não encontrado: {args.manifesto}")
    projeto = args.manifesto.parent

    titulo = args.titulo or _titulo_da_descricao(projeto)
    if not titulo:
        raise SystemExit(
            "Sem --titulo e sem descricao.md pra derivar o título automaticamente. "
            "Passe --titulo \"...\" explicitamente."
        )

    if args.imagem:
        imagem_fundo = args.imagem
        if not imagem_fundo.exists():
            raise SystemExit(f"Imagem não encontrada: {imagem_fundo}")
    else:
        if not args.prompt:
            raise SystemExit(
                "Sem --prompt e sem --imagem. A capa precisa de uma cena própria e chamativa "
                "(não reaproveita as imagens do corpo do vídeo) — escreva um --prompt em "
                "inglês descrevendo essa cena, ou passe --imagem apontando pra um "
                "capa_fundo.png já gerado antes."
            )
        workflow_path = args.workflow or WORKFLOW_PADRAO
        if not workflow_path.exists():
            raise SystemExit(f"Workflow do ComfyUI não encontrado: {workflow_path}")
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        imagem_fundo = projeto / "capa_fundo.png"
        print("Gerando fundo de capa no ComfyUI...")
        try:
            info = gerar_imagem(args.server, workflow, args.prompt, args.aspect_ratio, imagem_fundo)
        except requests.exceptions.ConnectionError as e:
            raise SystemExit(f"Não consegui falar com o ComfyUI em {args.server}. Ele está aberto?") from e
        (projeto / "capa_manifesto.json").write_text(
            json.dumps({"titulo": titulo, **info}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Fundo gerado: {imagem_fundo.name} (prompt: {info['prompt_final'][:100]}...)")

    destino = args.saida or projeto / "capa.png"
    print(f'Desenhando título "{titulo}" sobre {imagem_fundo.name}...')
    gerar_capa(imagem_fundo, titulo, destino, proporcao=args.proporcao)
    print(f"Pronto: {destino}")


if __name__ == "__main__":
    main()
