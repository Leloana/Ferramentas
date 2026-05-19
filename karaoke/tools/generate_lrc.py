import os
import sys
import argparse
import numpy as np
from pathlib import Path

# Adiciona o diretório server ao path para importar o stt_engine
sys.path.append(str(Path(__file__).parent.parent / "server"))
from stt_engine import STTEngine

def load_audio_full(path):
    """Carrega áudio completo e converte para numpy float32 16kHz mono usando PyAV."""
    import av
    container = av.open(str(path))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
    
    audio_data = []
    for frame in container.decode(stream):
        for resampled_frame in resampler.resample(frame):
            audio_data.append(resampled_frame.to_ndarray().flatten())
            
    for resampled_frame in resampler.resample(None):
        audio_data.append(resampled_frame.to_ndarray().flatten())
        
    return np.concatenate(audio_data)

def format_lrc_timestamp(seconds):
    """Converte segundos em formato de timestamp LRC [mm:ss.xx]"""
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"[{minutes:02d}:{remaining_seconds:05.2f}]"

def generate_lrc(song_dir, language="en"):
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
        
    print("Inicializando STT Engine com GPU...")
    engine = STTEngine(model_size="medium", device="auto")
    
    print("Transcrevendo áudio em segmentos e gerando timestamps...")
    # Transcreve usando o Whisper nativo da engine no nível de segmento
    segments, info = engine.model.transcribe(
    audio,
    language=language,
    beam_size=10,
    word_timestamps=False,
    vad_filter=True,
    vad_parameters={"min_silence_duration_ms": 500}
)
    
    lrc_lines = []
    # Metadados iniciais padrões do arquivo LRC
    lrc_lines.append(f"[ar: Artista]")
    lrc_lines.append(f"[ti: {song_path.name.replace('-', ' ').title()}]")
    lrc_lines.append("[length: --:--]")
    lrc_lines.append("")
    print(f"Duração total do áudio: {len(audio) / 16000:.2f}s")
    raw_segments = []
    for segment in segments:
        print(f"  RAW start={segment.start:.2f} end={segment.end:.2f} text={segment.text[:40]}")
        text = segment.text.strip()
        if not text:
            continue
        raw_segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": text
        })

    for seg in raw_segments:
        print(f"  RAW start={seg['start']:.2f} end={seg['end']:.2f} text={seg['text'][:40]}")

    # Mescla segmentos muito próximos (menos de 2s de diferença)
    merged = []
    for seg in raw_segments:
        if merged and (seg["start"] - merged[-1]["start"]) < 1.5:
            merged[-1]["text"] += " " + seg["text"]
            merged[-1]["end"] = seg["end"]
        else:
            merged.append({"start": seg["start"], "end": seg["end"], "text": seg["text"]})

    for seg in merged:
        timestamp = format_lrc_timestamp(seg["start"])
        lrc_line = f"{timestamp}{seg['text']}"
        print(f"  {lrc_line}")
        lrc_lines.append(lrc_line)
        
        # Adiciona marcador de fim de verso
        if seg.get("end") is not None:
            end_timestamp = format_lrc_timestamp(seg["end"])
            lrc_lines.append(end_timestamp)
        
    # Grava o lyrics.lrc sem linhas em branco e com quebras de linha limpas
    clean_lines = [line.strip() for line in lrc_lines if line.strip()]
    with open(lrc_output, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(clean_lines) + "\n")
        
    print(f"\nSucesso! Legenda LRC gerada em: {lrc_output}")
    print("Você já pode abrir e editar este arquivo para ajustar o texto e corrigir pequenos erros!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("song_dir", help="Pasta da música contendo vocal.mp3")
    parser.add_argument("--lang", default="en", help="Língua da música (ex: en, pt)")
    args = parser.parse_args()
    
    generate_lrc(args.song_dir, args.lang)
