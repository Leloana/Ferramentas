"""Monta um vídeo curto (uma imagem de fundo animada por frase + áudio +
legenda) a partir de uma parte já gerada por `gerar_video.py` +
`gerar_imagens.py`.

Uso:
    python scripts/montar_video.py Projetos/video-curto/humanidade_manifesto.json --parte 1

Fluxo:
1. Lê o áudio e o timestamp por frase daquela parte (do manifesto de
   `gerar_video.py`) e a imagem de fundo de cada frase (de
   `gerar_imagens.py`, uma por frase, mesma numeração, já no formato
   vertical final — sem folga lateral pra pan).
2. Renderiza um clipe mudo por frase: zoom lento (`zoompan`) sobre a
   imagem durante o tempo daquela frase — alternando entre zoom-in e
   zoom-out a cada frase pra variar o movimento entre uma imagem e outra.
3. Concatena os clipes (mesmo codec/resolução, concat por stream copy) e,
   numa segunda passada, junta o áudio original inteiro e queima a legenda
   sincronizada por cima.

Requer `ffmpeg` no PATH.
"""
from __future__ import annotations

import argparse
import json
import shutil
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


_ZOOM_MAX = 1.3
_FPS_CLIPE = 30
_SUPERSAMPLE = 4  # ver nota de tremor em renderizar_clipe_imagem


def _direcao_zoom(indice: int, efeito: str) -> str:
    if efeito == "alternar":
        return "zoom-in" if indice % 2 == 0 else "zoom-out"
    return efeito


def renderizar_clipe_imagem(imagem: Path, duracao: float, destino: Path, largura: int, altura: int, direcao: str) -> None:
    """Renderiza a imagem parada num clipe de `duracao` segundos com um zoom
    lento sobre ela (`zoompan`) — como as imagens já nascem no formato
    vertical final (sem folga lateral), o movimento aqui é por zoom, não
    por pan. `zoom-in` começa em 1.0x e termina em `_ZOOM_MAX`; `zoom-out`
    é o inverso. Interpolação linear em função do frame (`on`), não do
    incremento recursivo padrão do zoompan, pra bater exatamente com a
    duração pedida (que varia por frase).

    Escala pra `_SUPERSAMPLE`x a resolução final ANTES do zoompan — as
    imagens do ComfyUI nascem perto do tamanho final (768x1368 pra um
    vídeo de 1080x1920), e o zoompan recalcula a janela de corte em
    pixels inteiros a cada frame; numa imagem só um pouco maior que a
    saída, esse arredondamento é uma fração grande do deslocamento entre
    frames e o zoom sai tremido. Com a imagem de entrada bem maior, o
    mesmo arredondamento vira uma fração desprezível, e o `s=` final do
    zoompan reamostra pra baixo suavizando o resto.
    """
    frames = max(1, round(duracao * _FPS_CLIPE))
    if direcao == "zoom-in":
        z_expr = f"1.0+{_ZOOM_MAX - 1.0}*on/{frames}"
    else:
        z_expr = f"{_ZOOM_MAX}-{_ZOOM_MAX - 1.0}*on/{frames}"
    vf = (
        f"scale={largura * _SUPERSAMPLE}:{altura * _SUPERSAMPLE},"
        f"zoompan=z='{z_expr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={largura}x{altura}:fps={_FPS_CLIPE}"
    )
    comando = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(imagem.resolve()),
        "-t", f"{duracao:.3f}",
        "-vf", vf, "-frames:v", str(frames), "-pix_fmt", "yuv420p", "-an",
        str(destino.resolve()),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ao renderizar {destino.name}:\n{resultado.stderr[-3000:]}")


def montar(
    imagens: list[Path], frases: list[dict], audio: Path, destino: Path,
    proporcao: str = "9:16", efeito: str = "alternar",
) -> Path:
    if len(imagens) != len(frases):
        raise ValueError(f"{len(imagens)} imagem(ns) para {len(frases)} frase(s) — precisa ser 1 pra 1")

    largura, altura = _RESOLUCOES[proporcao]
    duracao_total = duracao_wav(audio)

    destino.parent.mkdir(parents=True, exist_ok=True)
    pasta_tmp = destino.parent / f"_tmp_{destino.stem}"
    pasta_tmp.mkdir(parents=True, exist_ok=True)
    try:
        # Cada imagem fica visível do início da sua frase até o início da
        # próxima (cobrindo também a pausa entre frases); a última cobre até
        # o fim real do áudio. Assim a soma das durações dos clipes bate
        # exatamente com a duração do áudio, sem precisar cortar nada com
        # -shortest na junção final.
        inicios = [f["inicio_s"] for f in frases]
        duracoes = [inicios[i + 1] - inicios[i] for i in range(len(inicios) - 1)]
        duracoes.append(duracao_total - inicios[-1])

        linhas_concat = []
        for i, (imagem, dur) in enumerate(zip(imagens, duracoes)):
            clipe = pasta_tmp / f"clipe_{i:02d}.mp4"
            renderizar_clipe_imagem(imagem, dur, clipe, largura, altura, _direcao_zoom(i, efeito))
            linhas_concat.append(f"file '{clipe.name}'")
        lista_concat = pasta_tmp / "lista.txt"
        lista_concat.write_text("\n".join(linhas_concat), encoding="utf-8")

        video_concat = pasta_tmp / "concat.mp4"
        resultado = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy", "concat.mp4"],
            cwd=pasta_tmp, capture_output=True, text=True,
        )
        if resultado.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao concatenar os clipes:\n{resultado.stderr[-3000:]}")

        caminho_srt = pasta_tmp / "legenda.srt"
        gerar_srt(dividir_em_legendas(frases), caminho_srt)

        # Aqui original_size = tamanho real do vídeo (largura x altura),
        # porque o concat.mp4 já chega no filtergraph nessa resolução — sem
        # scale/crop antes do subtitles nesta passada (ver gotcha no
        # CLAUDE.md: original_size é sempre o tamanho de entrada do
        # filtergraph naquele ponto, não o tamanho "final" em si).
        vf = f"subtitles=legenda.srt:original_size={largura}x{altura}:force_style='{_ESTILO_LEGENDA}'"
        comando = [
            "ffmpeg", "-y",
            "-i", str(video_concat.resolve()),
            "-i", str(audio.resolve()),
            "-vf", vf,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(destino.resolve()),
        ]
        resultado = subprocess.run(comando, cwd=pasta_tmp, capture_output=True, text=True)
        if resultado.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou na montagem final:\n{resultado.stderr[-4000:]}")
    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)

    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifesto", type=Path, help="Caminho do <nome>_manifesto.json gerado por gerar_video.py")
    ap.add_argument("--parte", type=int, default=1, help="Número da parte curta (1-based)")
    ap.add_argument("--proporcao", choices=sorted(_RESOLUCOES), default="9:16")
    ap.add_argument("--efeito", choices=["alternar", "zoom-in", "zoom-out"], default="alternar",
                     help="Zoom por imagem: alterna in/out a cada frase (padrão) ou fixa num só")
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
    if not audio.exists():
        raise SystemExit(f"Áudio não encontrado: {audio}")

    frases = parte["frases"]
    imagens = [projeto / "imagens" / f"{nome_base}_{args.parte:02d}_{j:02d}.png" for j in range(1, len(frases) + 1)]
    faltando = [str(p) for p in imagens if not p.exists()]
    if faltando:
        raise SystemExit(
            "Imagem(ns) não encontrada(s):\n" + "\n".join(faltando) +
            f"\nRode: python scripts/gerar_imagens.py {args.manifesto} --parte {args.parte}"
        )

    destino = args.saida or projeto / "montagem" / f"{nome_base}_{args.parte:02d}_{args.proporcao.replace(':', 'x')}.mp4"
    print(f"Montando {destino.name} ({args.proporcao}, {len(imagens)} imagem(ns), efeito {args.efeito})...")
    montar(imagens, frases, audio, destino, proporcao=args.proporcao, efeito=args.efeito)
    print(f"Pronto: {destino}")


if __name__ == "__main__":
    main()
