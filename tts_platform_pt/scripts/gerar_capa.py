"""Gera a imagem de capa (thumbnail) de um vídeo: reaproveita uma das imagens
de fundo já geradas por `gerar_imagens.py` e desenha o título por cima como
texto real — não pede pro modelo de difusão gerar o texto na imagem, porque
esse é justamente o bug conhecido do Krea2/ComfyUI usado aqui (texto
borrado/ilegível, ver `comfy/GOTCHAS.md` e `_REGRA_SEM_TEXTO` em
`gerar_imagens.py`). O texto é desenhado com Pillow (já é dependência
transitiva do projeto, via coqui-tts).

Uso:
    python scripts/gerar_capa.py Projetos/Video_1/historia_humanidade_parte2/texto_manifesto.json
    # sem --titulo, usa a 1a linha de descricao.md (sem o "👇" final)
    python scripts/gerar_capa.py Projetos/Video_1/historia_humanidade_parte2/texto_manifesto.json --titulo "História da Humanidade — Parte 2/5"
    # escolhendo outra imagem de fundo (padrão: a da frase 1)
    python scripts/gerar_capa.py Projetos/Video_1/historia_humanidade_parte2/texto_manifesto.json --frase 4

Saída: <projeto>/capa.png — um arquivo só por projeto, igual às imagens de
fundo (não depende de voz/manifesto, só do texto e da imagem escolhida).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

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
    ap.add_argument("--frase", type=int, default=1, help="Qual imagem de fundo usar (1-based). Padrão: 1")
    ap.add_argument("--imagem", type=Path, default=None, help="Caminho direto de uma imagem, sobrepõe --frase")
    ap.add_argument("--imagens-nome", default=None, help=(
        "Prefixo dos arquivos de imagem, se diferente do nome do roteiro deste manifesto "
        "(mesma flag/motivo de montar_video.py)."
    ))
    ap.add_argument("--proporcao", choices=sorted(_RESOLUCOES), default="9:16")
    ap.add_argument("--saida", type=Path, default=None)
    args = ap.parse_args()

    if not args.manifesto.exists():
        raise SystemExit(f"Manifesto não encontrado: {args.manifesto}")
    manifesto = json.loads(args.manifesto.read_text(encoding="utf-8"))
    projeto = args.manifesto.parent
    nome_base = Path(manifesto["roteiro"]).stem
    nome_imagens = args.imagens_nome or nome_base

    imagem_fundo = args.imagem or (projeto / "imagens" / f"{nome_imagens}_{args.frase:02d}.png")
    if not imagem_fundo.exists():
        raise SystemExit(
            f"Imagem não encontrada: {imagem_fundo}\n"
            f"Rode: python scripts/gerar_imagens.py {args.manifesto}"
        )

    titulo = args.titulo or _titulo_da_descricao(projeto)
    if not titulo:
        raise SystemExit(
            "Sem --titulo e sem descricao.md pra derivar o título automaticamente. "
            "Passe --titulo \"...\" explicitamente."
        )

    destino = args.saida or projeto / "capa.png"
    print(f'Gerando capa com título "{titulo}" sobre {imagem_fundo.name}...')
    gerar_capa(imagem_fundo, titulo, destino, proporcao=args.proporcao)
    print(f"Pronto: {destino}")


if __name__ == "__main__":
    main()
