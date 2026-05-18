import os
import json
import argparse
import numpy as np
from pathlib import Path
import av
import sys
import re

# Adiciona o diretório server ao path para importar o stt_engine
sys.path.append(str(Path(__file__).parent.parent / "server"))
from stt_engine import STTEngine, get_stt_engine

def parse_lrc(lrc_path):
    """Parseia arquivo LRC simples [mm:ss.xx] Letra e extrai tags de metadados como offset."""
    lines = []
    offset = 0.0  # em segundos
    with open(lrc_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip() or not line.startswith("["):
                continue
            try:
                # Verifica se é uma tag de metadados (como offset)
                if ":" in line and not line.startswith("[0") and not line.startswith("[1") and not line.startswith("[2"):
                    if "offset" in line.lower():
                        match = re.search(r'\[offset:\s*([\d\+\-]+)\]', line, re.IGNORECASE)
                        if match:
                            offset = float(match.group(1)) / 1000.0  # Converte ms para segundos
                    continue
                    
                time_part, text = line.split("]", 1)
                time_str = time_part[1:] # remove [
                m, s = time_str.split(":")
                timestamp = int(m) * 60 + float(s)
                
                # Ignora marcações de tempo vazias (como limpezas de tela do LRC tradicional)
                # que causariam segmentos fantasmas de curtíssima duração
                cleaned_text = text.strip()
                if not cleaned_text:
                    continue
                    
                lines.append({"start": timestamp, "text": cleaned_text})
            except:
                continue
    return sorted(lines, key=lambda x: x["start"]), offset

def load_audio_full(path):
    """Carrega áudio completo e converte para numpy float32 16kHz mono usando PyAV."""
    container = av.open(str(path))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
    
    audio_data = []
    for frame in container.decode(stream):
        for resampled_frame in resampler.resample(frame):
            audio_data.append(resampled_frame.to_ndarray().flatten())
    
    # Finaliza o resampler
    for resampled_frame in resampler.resample(None):
        audio_data.append(resampled_frame.to_ndarray().flatten())
        
    return np.concatenate(audio_data)

def prepare_song(song_dir, language="en"):
    song_path = Path(song_dir)
    vocal_mp3 = song_path / "vocal.mp3"
    lyrics_lrc = song_path / "lyrics.lrc"
    
    if not vocal_mp3.exists() or not lyrics_lrc.exists():
        print(f"Erro: Certifique-se que vocal.mp3 e lyrics.lrc existem em {song_dir}")
        return

    print(f"--- Processando: {song_path.name} ---")
    
    # 1. Parse LRC e extração de offset
    lrc_lines, offset = parse_lrc(lyrics_lrc)
    if not lrc_lines:
        print("Erro: Nenhum timestamp encontrado no LRC.")
        return

    if offset != 0.0:
        print(f"Aviso: Aplicando deslocamento global (offset) de {offset:.3f} segundos em todas as marcas de tempo.")

    # 2. Carregar Áudio Vocal completo via PyAV
    print("Carregando vocal.mp3 (usando PyAV)...")
    try:
        full_audio = load_audio_full(vocal_mp3)
    except Exception as e:
        print(f"Erro ao carregar áudio: {e}")
        return
        
    sample_rate = 16000
    
    # 3. Inicializar Engine (reutiliza singleton se rodando sob o server FastAPI)
    engine = get_stt_engine()
    
    segments_data = []
    
    for i, line in enumerate(lrc_lines):
        start_sample = int(line["start"] * sample_rate)
        if i < len(lrc_lines) - 1:
            end_sample = int(lrc_lines[i+1]["start"] * sample_rate)
        else:
            end_sample = len(full_audio)
            
        print(f"Segmento {i+1}/{len(lrc_lines)}: [{line['start']:.2f}s] {line['text']}")
        
        # Se a linha da letra for vazia, pula a transcrição e registra o segmento vazio
        if not line["text"].strip():
            s_start = max(0.0, round(line["start"] + offset, 3))
            s_end = max(0.0, round((end_sample / sample_rate) + offset, 3))
            p_end = max(0.0, round(((end_sample / sample_rate) + 0.5) + offset, 3))
            segments_data.append({
                "id": i + 1,
                "label": f"Parte {i + 1}",
                "sing_start": s_start,
                "sing_end": s_end,
                "pause_start": s_end,
                "pause_end": p_end,
                "language": language,
                "lyrics": "",
                "lyrics_timed": []
            })
            continue

        # Extrair trecho do numpy array
        # Para o último segmento, limita a captação a no máximo 15 segundos para evitar que o Whisper 
        # tente transcrever o silêncio instrumental final da música (o que causa alucinações e timing distorcido).
        is_last = (i == len(lrc_lines) - 1)
        if is_last:
            max_segment_samples = int(15 * sample_rate)
            segment_audio = full_audio[start_sample : min(end_sample, start_sample + max_segment_samples)]
        else:
            segment_audio = full_audio[start_sample:end_sample]
        
        # 3. Transcrever segmento
        _, words = engine.transcribe(segment_audio, language=language)
        
        # 4. Alinhamento inteligente (Smart Word Alignment)
        lyrics_timed = []
        official_words = line["text"].split()
        
        if words and len(words) > 0:
            # Temos timestamps do Whisper
            if len(words) == len(official_words):
                # Caso ideal: match 1:1 perfeito
                for idx, off_word in enumerate(official_words):
                    trans_word = words[idx]
                    t_start = trans_word["start"]
                    lyrics_timed.append({
                        "word": off_word,
                        "expected_start": round(t_start, 3)
                    })
            else:
                # Caso as contagens divirjam, usamos alinhamento por proximidade ou interpolação linear
                for idx, off_word in enumerate(official_words):
                    best_match_time = None
                    min_dist = 999.0
                    for trans_word in words:
                        dist = abs(trans_word["start"] - (idx / len(official_words)) * (segment_audio.size / sample_rate))
                        if dist < min_dist:
                            min_dist = dist
                            best_match_time = trans_word["start"]
                    
                    if best_match_time is not None:
                        lyrics_timed.append({
                            "word": off_word,
                            "expected_start": round(best_match_time, 3)
                        })
                    else:
                        ratio = idx / len(official_words)
                        t_start = ratio * (segment_audio.size / sample_rate)
                        lyrics_timed.append({
                            "word": off_word,
                            "expected_start": round(t_start, 3)
                        })
        else:
            # Fallback completo se o Whisper falhar: distribui uniformemente no tempo do segmento extraído
            max_duration = segment_audio.size / sample_rate
            n_off = len(official_words)
            for idx, off_word in enumerate(official_words):
                ratio = idx / n_off
                t_start = ratio * max_duration
                lyrics_timed.append({
                    "word": off_word,
                    "expected_start": round(t_start, 3)
                })
        
        # Garante que:
        # 1. Nenhuma palavra tenha expected_start menor que 0.05s
        # 2. Os tempos expected_start sejam estritamente crescentes (monotônicos com delta de 50ms)
        #    para evitar que palavras posteriores acendam antes de palavras anteriores no frontend!
        voice_delay = words[0]["start"] if words else 0.0
        if words:
            for w in lyrics_timed:
                w["expected_start"] = max(0.0, round(w["expected_start"] - voice_delay, 3))

        # 2. Garante mínimo de 0.05 na primeira palavra e monotônico
        if lyrics_timed:
            lyrics_timed[0]["expected_start"] = 0.05
            for idx in range(1, len(lyrics_timed)):
                min_start = round(lyrics_timed[idx - 1]["expected_start"] + 0.05, 3)
                if lyrics_timed[idx]["expected_start"] < min_start:
                    lyrics_timed[idx]["expected_start"] = min_start

        max_end = end_sample / sample_rate
        if words:
            actual_sing_end = line["start"] + words[-1]["end"]
            # Encerra o segmento de canto logo após a última palavra
            sing_end = min(actual_sing_end + 0.5, max_end)
            # Aciona a troca de interface quase imediatamente
            pause_end = min(sing_end + 0.1, max_end)
        else:
            sing_end = max_end
            pause_end = sing_end + 0.5
            
        # Aplica o offset global (deslocamento) salvando com proteção de limite mínimo (0.0s)
        s_start = max(0.0, round(line["start"] + offset + voice_delay, 3))
        s_end = max(0.0, round(sing_end + offset, 3))
        p_end = max(0.0, round(pause_end + offset, 3))
        
        segments_data.append({
            "id": i + 1,
            "label": f"Parte {i + 1}",
            "sing_start": s_start,
            "sing_end": s_end,
            "pause_start": s_end,
            "pause_end": p_end,
            "language": language,
            "lyrics": line["text"],
            "lyrics_timed": lyrics_timed
        })

    # Salvar segments.json
    output_path = song_path / "segments.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments_data, f, indent=2, ensure_ascii=False)
        
    print(f"\nSucesso! Gerado: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("song_dir", help="Pasta da música contendo vocal.mp3 e lyrics.lrc")
    parser.add_argument("--lang", default="en", help="Língua da música (ex: pt, en)")
    args = parser.parse_args()
    
    prepare_song(args.song_dir, args.lang)
