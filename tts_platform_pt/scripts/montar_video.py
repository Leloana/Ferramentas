"""Monta um vídeo curto (uma imagem de fundo animada por frase + áudio +
legenda) a partir do que já foi gerado por `gerar_video.py` +
`gerar_imagens.py`.

Uso:
    python scripts/montar_video.py Projetos/Video_1/historia_humanidade/texto_manifesto.json

Fluxo:
1. Lê o áudio e o timestamp por frase (do manifesto de `gerar_video.py`) e
   a imagem de fundo de cada frase (de `gerar_imagens.py`, uma por frase,
   mesma numeração, já no formato vertical final — sem folga lateral pra
   pan).
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
import re
import shutil
import subprocess
import wave
from pathlib import Path

_RESOLUCOES = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

_FONTE_LEGENDA = "Arial"
_TAMANHO_FONTE_LEGENDA = 52
_OUTLINE_LEGENDA = 3
_MARGEM_LR_LEGENDA = 140

_PALAVRAS_POR_LEGENDA = 4

# Mantém letras/dígitos/espaço/hífen (hífen interno de palavra composta, ex.
# "pós-guerra"), remove o resto (ponto, vírgula, aspas, dois-pontos,
# ponto-e-vírgula, travessão, reticências, parênteses...) — a legenda
# queimada no vídeo mostra só as palavras faladas, sem pontuação.
_PONTUACAO_LEGENDA_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def _limpar_pontuacao(texto: str) -> str:
    sem_pontuacao = _PONTUACAO_LEGENDA_RE.sub(" ", texto)
    return re.sub(r"\s+", " ", sem_pontuacao).strip()


def dividir_em_legendas(frases: list[dict], max_palavras: int = _PALAVRAS_POR_LEGENDA) -> list[dict]:
    """Quebra cada frase (uma entrada por sentença) em pedaços menores pra
    legenda de vídeo curto — uma frase inteira como cue única fica grande
    demais na tela e some devagar. Não temos timestamp por palavra (só por
    frase, vindo do motor), então a duração de cada pedaço é interpolada
    proporcionalmente à contagem de palavras dentro do intervalo conhecido
    da frase — aproximação razoável assumindo ritmo de fala ~constante
    dentro da frase, não uma medição real. Pontuação é removida antes de
    dividir em palavras (`_limpar_pontuacao`), senão um travessão solo
    entre espaços vira uma "palavra" falsa e desalinha a contagem."""
    legendas = []
    for frase in frases:
        palavras = _limpar_pontuacao(frase["texto"]).split()
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


def _formatar_tempo_ass(segundos: float) -> str:
    cs_total = round(segundos * 100)
    h, cs_total = divmod(cs_total, 360_000)
    m, cs_total = divmod(cs_total, 6_000)
    s, cs = divmod(cs_total, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


_CABECALHO_ASS = """[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {largura}
PlayResY: {altura}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fonte},{tamanho},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,{outline},0,5,{margem},{margem},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def gerar_ass(legendas: list[dict], destino: Path, largura: int, altura: int) -> None:
    """Gera o `.ass` diretamente (em vez de um `.srt` convertido pelo filtro
    `subtitles` do ffmpeg) porque essa conversão automática não estava
    respeitando a resolução real do vídeo pra escalar a fonte — o texto saía
    muito maior que `_TAMANHO_FONTE_LEGENDA` e ignorava o alinhamento central
    (`Alignment=5`), renderizando sempre grudado no topo. Com `PlayResX`/
    `PlayResY` batendo exatamente com `largura`/`altura` de saída, o libass
    usa o tamanho de fonte e a posição do estilo sem nenhum fator de escala
    implícito. `WrapStyle: 2` desliga quebra de linha automática — como cada
    legenda já vem limitada a `_PALAVRAS_POR_LEGENDA` palavras, o texto some
    da tela inteiro numa linha só em vez de quebrar."""
    cabecalho = _CABECALHO_ASS.format(
        largura=largura, altura=altura, fonte=_FONTE_LEGENDA,
        tamanho=_TAMANHO_FONTE_LEGENDA, outline=_OUTLINE_LEGENDA,
        margem=_MARGEM_LR_LEGENDA,
    )
    linhas = [cabecalho]
    for legenda in legendas:
        inicio = _formatar_tempo_ass(legenda["inicio_s"])
        fim = _formatar_tempo_ass(legenda["fim_s"])
        texto = legenda["texto"].replace("\n", " ")
        linhas.append(f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}\n")
    destino.write_text("".join(linhas), encoding="utf-8")


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

        caminho_ass = pasta_tmp / "legenda.ass"
        gerar_ass(dividir_em_legendas(frases), caminho_ass, largura, altura)

        vf = "ass=legenda.ass"
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
    ap.add_argument("--proporcao", choices=sorted(_RESOLUCOES), default="9:16")
    ap.add_argument("--efeito", choices=["alternar", "zoom-in", "zoom-out"], default="alternar",
                     help="Zoom por imagem: alterna in/out a cada frase (padrão) ou fixa num só")
    ap.add_argument("--saida", type=Path, default=None)
    ap.add_argument("--imagens-nome", default=None, help=(
        "Prefixo dos arquivos de imagem, se diferente do nome do roteiro "
        "deste manifesto — pra reaproveitar as mesmas imagens já geradas "
        "quando só a voz muda (mesmo texto/frases, sem duplicar arquivo)."
    ))
    args = ap.parse_args()

    if not args.manifesto.exists():
        raise SystemExit(f"Manifesto não encontrado: {args.manifesto}")
    manifesto = json.loads(args.manifesto.read_text(encoding="utf-8"))
    projeto = args.manifesto.parent
    nome_base = Path(manifesto["roteiro"]).stem
    nome_imagens = args.imagens_nome or nome_base
    if "frases" not in manifesto:
        raise SystemExit(
            "O manifesto não tem timestamps por frase "
            "(rode gerar_video.py de novo pra regerar com a versão atual do motor)."
        )

    audio = projeto / manifesto["arquivo"]
    if not audio.exists():
        raise SystemExit(f"Áudio não encontrado: {audio}")

    frases = manifesto["frases"]
    imagens = [projeto / "imagens" / f"{nome_imagens}_{j:02d}.png" for j in range(1, len(frases) + 1)]
    faltando = [str(p) for p in imagens if not p.exists()]
    if faltando:
        raise SystemExit(
            "Imagem(ns) não encontrada(s):\n" + "\n".join(faltando) +
            f"\nRode: python scripts/gerar_imagens.py {args.manifesto}"
        )

    destino = args.saida or projeto / "video" / f"{nome_base}_{args.proporcao.replace(':', 'x')}.mp4"
    print(f"Montando {destino.name} ({args.proporcao}, {len(imagens)} imagem(ns), efeito {args.efeito})...")
    montar(imagens, frases, audio, destino, proporcao=args.proporcao, efeito=args.efeito)
    print(f"Pronto: {destino}")


if __name__ == "__main__":
    main()
