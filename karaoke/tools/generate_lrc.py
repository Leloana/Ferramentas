"""CLI: gera um `lyrics.lrc` rascunho transcrevendo o `vocal.mp3` com o Whisper.

Usado como fallback no `reinstall_song.py` quando o alinhamento com
letra plana falha. Antes definia parâmetros VAD próprios (divergentes
de `whisper_params.TRANSCRIBE_KWARGS`) e instanciava um `STTEngine`
novo do zero — agora reaproveita o singleton do servidor para não
carregar um segundo modelo na VRAM.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Adiciona o diretório `server/` ao path para importar utilitários compartilhados.
sys.path.append(str(Path(__file__).resolve().parent.parent / "server"))

from stt_engine import get_stt_engine
from utils.audio import load_audio_full
from utils.whisper_params import TRANSCRIBE_KWARGS


def format_lrc_timestamp(seconds: float) -> str:
    """Converte segundos em formato de timestamp LRC `[mm:ss.xx]`."""
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"[{minutes:02d}:{remaining_seconds:05.2f}]"


def generate_lrc(song_dir: str, language: str = "en") -> None:
    song_path = Path(song_dir)
    vocal_mp3 = song_path / "vocal.mp3"
    lrc_output = song_path / "lyrics.lrc"

    if not vocal_mp3.exists():
        print(f"Erro: Certifique-se de que vocal.mp3 existe em {song_dir}")
        return

    print(f"--- Gerando LRC Automático para: {song_path.name} ---")
    print("Carregando áudio vocal (usando PyAV)...")
    try:
        audio = load_audio_full(vocal_mp3)
    except Exception as e:
        print(f"Erro ao carregar áudio: {e}")
        return

    print("Reutilizando STT Engine singleton...")
    engine = get_stt_engine()

    print("Transcrevendo áudio em segmentos e gerando timestamps...")
    # Mesmos parâmetros de VAD usados pelo upload e reinstall — antes
    # divergiam (threshold=0.3, min_silence=2000ms) e o LRC gerado por
    # este fallback ficava com versos colados.
    segments, _info = engine.model.transcribe(
        audio,
        language=language,
        **TRANSCRIBE_KWARGS,
    )

    lrc_lines: list[str] = [
        "[ar: Artista]",
        f"[ti: {song_path.name.replace('-', ' ').title()}]",
        "[length: --:--]",
        "",
    ]

    raw_segments = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        raw_segments.append({"start": segment.start, "end": segment.end, "text": text})

    # Mescla segmentos com gap de silêncio < 0.8s (evita fragmentos curtos demais).
    merged: list[dict] = []
    for seg in raw_segments:
        if merged and (seg["start"] - merged[-1]["end"]) < 0.8:
            merged[-1]["text"] += " " + seg["text"]
            merged[-1]["end"] = seg["end"]
        else:
            merged.append({"start": seg["start"], "end": seg["end"], "text": seg["text"]})

    for seg in merged:
        lrc_lines.append(f"{format_lrc_timestamp(seg['start'])}{seg['text']}")
        # Marcador de fim de verso: linha só com timestamp vira pausa no LRC.
        lrc_lines.append(f"{format_lrc_timestamp(seg['end'])} ")

    clean_lines = [line.strip() for line in lrc_lines if line.strip()]
    with open(lrc_output, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(clean_lines) + "\n")

    print(f"\nSucesso! Legenda LRC gerada em: {lrc_output}")
    print("Você já pode abrir e editar este arquivo para ajustar o texto.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("song_dir", help="Pasta da música contendo vocal.mp3")
    parser.add_argument("--lang", default="en", help="Língua da música (ex: en, pt)")
    args = parser.parse_args()
    generate_lrc(args.song_dir, args.lang)
