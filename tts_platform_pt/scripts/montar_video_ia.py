"""Monta um vídeo curto (um clipe de vídeo gerado por IA por frase + áudio +
legenda) a partir do que já foi gerado por `gerar_video.py` + clipes de
vídeo externos (ex.: gerados na nuvem, um por frase, sem depender do
ComfyUI/`gerar_imagens.py`).

Uso:
    python scripts/montar_video_ia.py Projetos/ideias/<nome>/texto_manifesto.json

Fluxo:
1. Lê o áudio e o timestamp por frase (do manifesto de `gerar_video.py`) e
   os clipes de vídeo de cada frase (um por frase, mesma numeração 1-based
   usada por `gerar_imagens.py` pra imagens: `<nome>_FF.mp4`).
2. Recorta/estica cada clipe pra bater exatamente a duração daquela frase
   (o conteúdo do clipe não precisa corresponder ao texto — só a duração
   importa pra manter a narração sincronizada) e descarta o áudio original
   do clipe.
3. Concatena os clipes (mesmo codec/resolução, concat por stream copy) e,
   numa segunda passada, junta o áudio da narração inteiro e queima a
   legenda sincronizada por cima — mesma lógica de legenda de
   `montar_video.py`, reaproveitada daqui.

Requer `ffmpeg`/`ffprobe` no PATH.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from montar_video import (
    _RESOLUCOES, _FPS_CLIPE, _direcao_zoom, dividir_em_legendas, duracao_wav,
    gerar_ass, renderizar_clipe_imagem,
)

# Abaixo disso o clipe já cobre a frase inteira (ou falta menos que 1
# frame perceptível) — não vale montar a cauda com zoom pra economia
# irrisória de tempo de render.
_LIMIAR_PAD_ZOOM_S = 0.05
# Fade final (vídeo + áudio) pra o vídeo não terminar num corte seco.
_FADE_SAIDA_S = 0.6


def _duracao_video(caminho: Path) -> float:
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(caminho.resolve())],
        capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"ffprobe falhou em {caminho.name}:\n{resultado.stderr[-2000:]}")
    return float(resultado.stdout.strip())


def _rodar_ffmpeg(comando: list[str], contexto: str, cwd: Path | None = None) -> None:
    resultado = subprocess.run(comando, cwd=cwd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou em {contexto}:\n{resultado.stderr[-3000:]}")


def renderizar_clipe_video(
    clipe_ia: Path, duracao: float, destino: Path, largura: int, altura: int,
    manter_audio: bool, indice: int,
) -> None:
    """Recorta (cover crop, sem esticar) e ajusta a duração de um clipe de
    vídeo externo pra bater exatamente a duração da frase correspondente —
    mesmo contrato de `renderizar_clipe_imagem` em `montar_video.py`,
    necessário pra manter a troca de cena sincronizada com a narração.
    Clipe mais longo que a frase é cortado a partir do início.

    Clipe mais curto que a frase NÃO fica parado — um `tpad` puro (frame
    congelado) tem cara de trava no meio do vídeo. Em vez disso, o trecho
    real do clipe é seguido de uma cauda com zoom lento sobre o último
    frame dele (reaproveitando `renderizar_clipe_imagem`/`_direcao_zoom`
    de `montar_video.py`, a mesma técnica já usada nas imagens estáticas),
    mantendo alguma sensação de movimento até o fim da frase.

    `manter_audio=False` descarta o áudio original do clipe (`-an`).
    `manter_audio=True` preserva o áudio do trecho real e completa a cauda
    com silêncio (`anullsrc`), recodificado num formato fixo
    (`aac`/44.1kHz/estéreo) pra concat por stream copy funcionar mesmo se
    os clipes originais tiverem taxas diferentes entre si."""
    origem_dur = _duracao_video(clipe_ia)
    dur_real = min(origem_dur, duracao)
    pad = duracao - dur_real

    vf_base = (
        f"scale={largura}:{altura}:force_original_aspect_ratio=increase,"
        f"crop={largura}:{altura},fps={_FPS_CLIPE},setsar=1"
    )

    if pad <= _LIMIAR_PAD_ZOOM_S:
        comando = ["ffmpeg", "-y", "-i", str(clipe_ia.resolve())]
        if manter_audio:
            comando += [
                "-vf", vf_base, "-af", "apad", "-t", f"{duracao:.3f}",
                "-pix_fmt", "yuv420p", "-c:v", "libx264",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
            ]
        else:
            comando += [
                "-an", "-vf", vf_base, "-t", f"{duracao:.3f}",
                "-pix_fmt", "yuv420p", "-c:v", "libx264",
            ]
        comando.append(str(destino.resolve()))
        _rodar_ffmpeg(comando, clipe_ia.name)
        return

    pasta_tmp = destino.parent
    trecho_real = pasta_tmp / f"{destino.stem}_real.mp4"
    ultimo_frame = pasta_tmp / f"{destino.stem}_ultimoframe.png"
    cauda_zoom = pasta_tmp / f"{destino.stem}_cauda.mp4"

    comando_real = ["ffmpeg", "-y", "-i", str(clipe_ia.resolve())]
    if manter_audio:
        comando_real += [
            "-vf", vf_base, "-t", f"{dur_real:.3f}",
            "-pix_fmt", "yuv420p", "-c:v", "libx264",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
        ]
    else:
        comando_real += [
            "-an", "-vf", vf_base, "-t", f"{dur_real:.3f}",
            "-pix_fmt", "yuv420p", "-c:v", "libx264",
        ]
    comando_real.append(str(trecho_real.resolve()))
    _rodar_ffmpeg(comando_real, clipe_ia.name)

    _rodar_ffmpeg([
        "ffmpeg", "-y", "-sseof", "-0.1", "-i", str(trecho_real.resolve()),
        "-frames:v", "1", str(ultimo_frame.resolve()),
    ], f"{clipe_ia.name} (extrair último frame)")

    renderizar_clipe_imagem(ultimo_frame, pad, cauda_zoom, largura, altura, _direcao_zoom(indice, "alternar"))

    if manter_audio:
        cauda_com_audio = pasta_tmp / f"{destino.stem}_caudaaudio.mp4"
        _rodar_ffmpeg([
            "ffmpeg", "-y", "-i", str(cauda_zoom.resolve()),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest", "-c:v", "copy", "-c:a", "aac",
            str(cauda_com_audio.resolve()),
        ], f"{clipe_ia.name} (silêncio na cauda)")
        cauda_zoom = cauda_com_audio

    lista = pasta_tmp / f"{destino.stem}_lista.txt"
    lista.write_text(f"file '{trecho_real.name}'\nfile '{cauda_zoom.name}'\n", encoding="utf-8")
    _rodar_ffmpeg(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista.name, "-c", "copy", destino.name],
        f"{clipe_ia.name} (juntar trecho real + cauda)", cwd=pasta_tmp,
    )


def montar(
    clipes: list[Path], frases: list[dict], audio: Path, destino: Path,
    proporcao: str = "9:16", volume_audio_ia: float | None = None,
) -> Path:
    if len(clipes) != len(frases):
        raise ValueError(f"{len(clipes)} clipe(s) para {len(frases)} frase(s) — precisa ser 1 pra 1")

    largura, altura = _RESOLUCOES[proporcao]
    duracao_total = duracao_wav(audio)

    destino.parent.mkdir(parents=True, exist_ok=True)
    pasta_tmp = destino.parent / f"_tmp_{destino.stem}"
    pasta_tmp.mkdir(parents=True, exist_ok=True)
    try:
        # Mesma lógica de `montar_video.montar`: cada clipe cobre do início
        # da sua frase até o início da próxima (inclui a pausa entre
        # frases), a última cobre até o fim real do áudio — soma das
        # durações bate exatamente com o áudio, sem precisar de -shortest
        # na junção dos clipes.
        inicios = [f["inicio_s"] for f in frases]
        duracoes = [inicios[i + 1] - inicios[i] for i in range(len(inicios) - 1)]
        duracoes.append(duracao_total - inicios[-1])

        manter_audio = volume_audio_ia is not None
        linhas_concat = []
        for i, (clipe_ia, dur) in enumerate(zip(clipes, duracoes)):
            clipe = pasta_tmp / f"clipe_{i:02d}.mp4"
            renderizar_clipe_video(clipe_ia, dur, clipe, largura, altura, manter_audio, i)
            linhas_concat.append(f"file '{clipe.name}'")
        lista_concat = pasta_tmp / "lista.txt"
        lista_concat.write_text("\n".join(linhas_concat), encoding="utf-8")

        video_concat = pasta_tmp / "concat.mp4"
        _rodar_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy", "concat.mp4"],
            "concatenar os clipes", cwd=pasta_tmp,
        )

        caminho_ass = pasta_tmp / "legenda.ass"
        gerar_ass(dividir_em_legendas(frases), caminho_ass, largura, altura)

        # Fade de vídeo+áudio nos últimos `_FADE_SAIDA_S` segundos — sem
        # isso o vídeo termina num corte seco (último frame direto pro
        # nada), sensação de "acabou de repente".
        fade_inicio = max(0.0, duracao_total - _FADE_SAIDA_S)
        fade_video = f"fade=t=out:st={fade_inicio:.3f}:d={_FADE_SAIDA_S}"
        fade_audio = f"afade=t=out:st={fade_inicio:.3f}:d={_FADE_SAIDA_S}"

        comando = [
            "ffmpeg", "-y",
            "-i", str(video_concat.resolve()),
            "-i", str(audio.resolve()),
        ]
        if manter_audio:
            # amix normaliza (reduz) o volume de ambas as entradas por
            # padrão pra evitar clipping na soma — normalize=0 desliga
            # isso, senão a narração também sairia abafada junto com o
            # áudio de fundo. duration=longest evita cortar a narração
            # caso ela seja alguns frames mais longa que o áudio de fundo
            # (a diferença real é coberta pelo -shortest final, que corta
            # ambos no tamanho do vídeo, igual ao modo sem áudio de fundo).
            filtro = (
                f"[0:v]ass=legenda.ass,{fade_video}[vout];"
                f"[0:a]volume={volume_audio_ia}[bg];"
                f"[1:a]anull[narr];"
                f"[bg][narr]amix=inputs=2:duration=longest:normalize=0,{fade_audio}[aout]"
            )
        else:
            filtro = (
                f"[0:v]ass=legenda.ass,{fade_video}[vout];"
                f"[1:a]{fade_audio}[aout]"
            )
        comando += [
            "-filter_complex", filtro, "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(destino.resolve()),
        ]
        _rodar_ffmpeg(comando, "montagem final", cwd=pasta_tmp)
    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)

    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifesto", type=Path, help="Caminho do <nome>_manifesto.json gerado por gerar_video.py")
    ap.add_argument("--clipes-dir", type=Path, default=None, help=(
        "Pasta com os clipes de vídeo por frase (padrão: <projeto>/clipes_ia/)"
    ))
    ap.add_argument("--clipes-nome", default=None, help=(
        "Prefixo dos arquivos de clipe, se diferente do nome do roteiro deste "
        "manifesto (mesma lógica de --imagens-nome em montar_video.py)."
    ))
    ap.add_argument("--proporcao", choices=sorted(_RESOLUCOES), default="9:16")
    ap.add_argument("--audio-ia-volume", type=float, default=None, help=(
        "Mantém o áudio original dos clipes de IA como fundo, misturado com "
        "a narração nesse volume relativo (0.0-1.0, ex.: 0.2 = 20%%). Sem "
        "essa flag (padrão), o áudio dos clipes é descartado."
    ))
    ap.add_argument("--saida", type=Path, default=None)
    args = ap.parse_args()

    if not args.manifesto.exists():
        raise SystemExit(f"Manifesto não encontrado: {args.manifesto}")
    manifesto = json.loads(args.manifesto.read_text(encoding="utf-8"))
    projeto = args.manifesto.parent
    nome_base = Path(manifesto["roteiro"]).stem
    nome_clipes = args.clipes_nome or nome_base
    if "frases" not in manifesto:
        raise SystemExit(
            "O manifesto não tem timestamps por frase "
            "(rode gerar_video.py de novo pra regerar com a versão atual do motor)."
        )

    audio = projeto / manifesto["arquivo"]
    if not audio.exists():
        raise SystemExit(f"Áudio não encontrado: {audio}")

    frases = manifesto["frases"]
    pasta_clipes = args.clipes_dir or (projeto / "clipes_ia")
    clipes = [pasta_clipes / f"{nome_clipes}_{j:02d}.mp4" for j in range(1, len(frases) + 1)]
    faltando = [str(p) for p in clipes if not p.exists()]
    if faltando:
        raise SystemExit(
            "Clipe(s) de vídeo não encontrado(s):\n" + "\n".join(faltando) +
            f"\nGere os clipes (ex.: Gemini) e salve em {pasta_clipes}/, um por "
            f"frase, nomeados {nome_clipes}_01.mp4, {nome_clipes}_02.mp4, ..."
        )

    sufixo = "_ia" if args.audio_ia_volume is None else "_ia_audiofundo"
    destino = args.saida or projeto / "video" / f"{nome_base}_{args.proporcao.replace(':', 'x')}{sufixo}.mp4"
    print(f"Montando {destino.name} ({args.proporcao}, {len(clipes)} clipe(s) de vídeo IA)...")
    montar(clipes, frases, audio, destino, proporcao=args.proporcao, volume_audio_ia=args.audio_ia_volume)
    print(f"Pronto: {destino}")


if __name__ == "__main__":
    main()
