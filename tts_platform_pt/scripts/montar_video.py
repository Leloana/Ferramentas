"""Monta um vídeo curto (imagem de fundo animada + áudio + legenda) a partir
de uma parte já gerada por `gerar_video.py` + `gerar_imagens.py`.

Uso:
    python scripts/montar_video.py Projetos/video-curto/humanidade_manifesto.json --parte 1

Fluxo:
1. Lê o áudio e o timestamp por frase daquela parte (do manifesto de
   `gerar_video.py`) e a imagem de fundo correspondente (de
   `gerar_imagens.py`, mesma numeração).
2. Gera um `.srt` com as legendas sincronizadas.
3. Monta o vídeo com ffmpeg: a imagem (16:9, gerada mais larga que o alvo)
   desliza lateralmente ("efeito Ken Burns" de pan) atrás do formato vertical
   pedido, com a legenda queimada por cima.

Requer `ffmpeg` no PATH.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import wave
from pathlib import Path

_RESOLUCOES = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

_ESTILO_LEGENDA = (
    "FontName=Arial,FontSize=32,Bold=1,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=0,"
    "Alignment=2,MarginL=80,MarginR=80,MarginV=140"
)

_PALAVRAS_POR_LEGENDA = 6


def dividir_em_legendas(frases: list[dict], max_palavras: int = _PALAVRAS_POR_LEGENDA) -> list[dict]:
    """Quebra cada frase (uma entrada por sentença) em pedaços menores pra
    legenda de vídeo curto — uma frase inteira como cue única fica grande
    demais na tela e some devagar. Não temos timestamp por palavra (só por
    frase, vindo do motor), então a duração de cada pedaço é interpolada
    proporcionalmente à contagem de palavras dentro do intervalo conhecido
    da frase — aproximação razoável assumindo ritmo de fala ~constante
    dentro da frase, não uma medição real."""
    legendas = []
    for frase in frases:
        palavras = frase["texto"].split()
        duracao_total = frase["fim_s"] - frase["inicio_s"]
        n_chunks = max(1, -(-len(palavras) // max_palavras))
        tam_chunk = -(-len(palavras) // n_chunks)
        cursor = frase["inicio_s"]
        for i in range(0, len(palavras), tam_chunk):
            chunk = palavras[i:i + tam_chunk]
            duracao_chunk = duracao_total * (len(chunk) / len(palavras))
            legendas.append({
                "texto": " ".join(chunk),
                "inicio_s": cursor,
                "fim_s": cursor + duracao_chunk,
            })
            cursor += duracao_chunk
    return legendas


def duracao_wav(caminho: Path) -> float:
    with wave.open(str(caminho), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def dimensoes_imagem(caminho: Path) -> tuple[int, int]:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(caminho)],
        capture_output=True, text=True, check=True,
    )
    largura, altura = saida.stdout.strip().split(",")
    return int(largura), int(altura)


def _formatar_tempo_srt(segundos: float) -> str:
    ms_total = round(segundos * 1000)
    h, ms_total = divmod(ms_total, 3_600_000)
    m, ms_total = divmod(ms_total, 60_000)
    s, ms = divmod(ms_total, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def gerar_srt(frases: list[dict], destino: Path) -> None:
    linhas = []
    for i, frase in enumerate(frases, start=1):
        linhas.append(str(i))
        linhas.append(f"{_formatar_tempo_srt(frase['inicio_s'])} --> {_formatar_tempo_srt(frase['fim_s'])}")
        linhas.append(frase["texto"])
        linhas.append("")
    destino.write_text("\n".join(linhas), encoding="utf-8")


def montar(
    imagem: Path, audio: Path, frases: list[dict], destino: Path, proporcao: str = "9:16", efeito: str = "pan-direita"
) -> Path:
    largura, altura = _RESOLUCOES[proporcao]
    duracao = duracao_wav(audio)
    img_largura, img_altura = dimensoes_imagem(imagem)

    destino.parent.mkdir(parents=True, exist_ok=True)
    caminho_srt = destino.parent / f"_legenda_{destino.stem}.srt"
    gerar_srt(dividir_em_legendas(frases), caminho_srt)

    # A imagem é gerada em 16:9 (mais larga que o alvo vertical); escalamos
    # pra bater a altura do vídeo e deslizamos uma janela do tamanho final
    # da esquerda pra direita (ou o inverso) ao longo da duração do áudio —
    # dá movimento sem precisar de várias imagens por parte.
    progresso = "t/{:.3f}".format(duracao) if efeito == "pan-direita" else "(1-t/{:.3f})".format(duracao)
    expr_x = f"min(max((iw-{largura})*({progresso}),0),iw-{largura})"
    # original_size do filtro subtitles é o tamanho do frame de ENTRADA do
    # filtergraph (a imagem original, antes do scale/crop) — não o tamanho
    # final pós-crop, apesar do nome sugerir isso e de ser fácil supor o
    # contrário. Passar o tamanho final ali (testado) faz o libass calcular
    # a escala errada e o texto sai gigante e mal posicionado, mesmo com
    # FontSize pequeno no force_style. Confirmado isolando o problema:
    # comparei renderizações com original_size = tamanho pós-crop (quebrado)
    # vs tamanho da imagem de entrada (correto) usando a mesma cadeia de
    # filtros — só a segunda opção posiciona e dimensiona certo.
    vf = (
        f"scale=-2:{altura},"
        f"crop={largura}:{altura}:x='{expr_x}':y=0,"
        f"subtitles={caminho_srt.name}:original_size={img_largura}x{img_altura}:force_style='{_ESTILO_LEGENDA}'"
    )

    comando = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(imagem.resolve()),
        "-i", str(audio.resolve()),
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(destino.resolve()),
    ]
    resultado = subprocess.run(comando, cwd=destino.parent, capture_output=True, text=True)
    caminho_srt.unlink(missing_ok=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou:\n{resultado.stderr[-4000:]}")
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifesto", type=Path, help="Caminho do <nome>_manifesto.json gerado por gerar_video.py")
    ap.add_argument("--parte", type=int, default=1, help="Número da parte curta (1-based)")
    ap.add_argument("--proporcao", choices=sorted(_RESOLUCOES), default="9:16")
    ap.add_argument("--efeito", choices=["pan-direita", "pan-esquerda"], default="pan-direita")
    ap.add_argument("--saida", type=Path, default=None)
    args = ap.parse_args()

    if not args.manifesto.exists():
        raise SystemExit(f"Manifesto não encontrado: {args.manifesto}")
    manifesto = json.loads(args.manifesto.read_text(encoding="utf-8"))
    projeto = args.manifesto.parent
    nome_base = Path(manifesto["roteiro"]).stem
    partes = manifesto["video_curto"]
    if not (1 <= args.parte <= len(partes)):
        raise SystemExit(f"--parte deve estar entre 1 e {len(partes)}")
    parte = partes[args.parte - 1]
    if "frases" not in parte:
        raise SystemExit(
            f"A parte {args.parte} não tem timestamps por frase no manifesto "
            "(rode gerar_video.py de novo pra regerar com a versão atual do motor)."
        )

    audio = projeto / "video-curto" / parte["arquivo"]
    imagem = projeto / "imagens" / f"{nome_base}_{args.parte:02d}.png"
    if not audio.exists():
        raise SystemExit(f"Áudio não encontrado: {audio}")
    if not imagem.exists():
        raise SystemExit(f"Imagem não encontrada: {imagem}")

    destino = args.saida or projeto / "montagem" / f"{nome_base}_{args.parte:02d}_{args.proporcao.replace(':', 'x')}.mp4"
    n_legendas = len(dividir_em_legendas(parte["frases"]))
    print(f"Montando {destino.name} ({args.proporcao}, efeito {args.efeito}, {n_legendas} legenda(s))...")
    montar(imagem, audio, parte["frases"], destino, proporcao=args.proporcao, efeito=args.efeito)
    print(f"Pronto: {destino}")


if __name__ == "__main__":
    main()
