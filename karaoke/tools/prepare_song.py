import argparse
import json
import sys
from pathlib import Path

# Adiciona o diretório server ao path para importar utilitários compartilhados.
sys.path.append(str(Path(__file__).parent.parent / "server"))

# Limpa PATH e registra DLLs do CUDA para evitar conflitos no Windows
import utils.cuda_bootstrap  # noqa: F401
import torch  # noqa: F401 (Força carregamento de DLLs do PyTorch/cuDNN primeiro)
import torchaudio  # noqa: F401

from lyrics_text import is_japanese, regroup_timed_words, split_words, time_words_by_characters
from stt_engine import get_stt_engine
from utils.audio import load_audio_full
from utils.segment_timing import finalize_segments, match_words_in_order
from utils.whisper_params import WHISPER_SR

import re

import numpy as np


LRC_STAMP_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(lrc_path):
    lines = []
    end_marks = []
    offset = 0.0
    with open(lrc_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip() or not line.startswith("["):
                continue
            try:
                if ":" in line and not line.startswith("[0") and not line.startswith("[1") and not line.startswith("[2"):
                    if "offset" in line.lower():
                        match = re.search(r'\[offset:\s*([\d\+\-]+)\]', line, re.IGNORECASE)
                        if match:
                            offset = float(match.group(1)) / 1000.0
                    continue

                # "[00:12.00][01:30.00]refrão": a mesma letra em várias marcas
                stamps = []
                rest = line
                while True:
                    m_ts = LRC_STAMP_RE.match(rest)
                    if not m_ts:
                        break
                    stamps.append(int(m_ts.group(1)) * 60 + float(m_ts.group(2)))
                    rest = rest[m_ts.end():]
                if not stamps:
                    continue
                cleaned_text = rest.strip()

                if not cleaned_text:
                    # marca vazia = fim do verso anterior (pausa); resolvida após ordenar
                    end_marks.extend(stamps)
                    continue

                for timestamp in stamps:
                    lines.append({"start": timestamp, "text": cleaned_text, "end": None})
            except Exception:
                continue

    lines.sort(key=lambda x: x["start"])
    for mark in end_marks:
        before = [ln for ln in lines if ln["start"] < mark]
        if before and before[-1]["end"] is None:
            before[-1]["end"] = mark
    return lines, offset


def prepare_song(song_dir, language="en", debug=False):
    song_path = Path(song_dir)
    vocal_mp3 = song_path / "vocal.mp3"
    if debug:
        lyrics_lrc = song_path / "lyrics_debug.lrc"
    else:
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
        
    sample_rate = WHISPER_SR
    
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
        # Limitamos a captação a no máximo 18 segundos para evitar que o Whisper tente transcrever silêncios
        # longos, solos instrumentais ou pontes (o que causa alucinações de repetição, travamentos ou lentidão).
        max_segment_samples = int(18 * sample_rate)
        segment_audio = full_audio[start_sample : min(end_sample, start_sample + max_segment_samples)]
        
        # 3. Transcrever segmento (passando a letra esperada como initial_prompt para guiar a IA)
        _, words = engine.transcribe(segment_audio, language=language, initial_prompt=line["text"])
        
        # 4. Alinhamento inteligente (Smart Word Alignment)
        lyrics_timed = []
        official_words = split_words(line["text"], language)

        if words and is_japanese(language):
            # Japonês: o Whisper devolve pedaços de 1–3 caracteres que não coincidem
            # com as unidades da letra (bunsetsu); os tempos vêm caractere a caractere.
            for w in time_words_by_characters(line["text"], language, words):
                lyrics_timed.append({
                    "word": w["word"],
                    "expected_start": round(w["start"], 3),
                    "expected_end": round(w["end"], 3),
                })
        elif words and len(words) > 0:
            # Temos timestamps do Whisper
            if len(words) == len(official_words):
                # Caso ideal: match 1:1 perfeito
                for idx, off_word in enumerate(official_words):
                    trans_word = words[idx]
                    t_start = trans_word["start"]
                    t_end = trans_word["end"]
                    lyrics_timed.append({
                        "word": off_word,
                        "expected_start": round(t_start, 3),
                        "expected_end": round(t_end, 3)
                    })
            else:
                # Contagens diferentes: casamento que respeita a ordem + interpolação
                # por sílabas (antes: "palavra do Whisper mais próxima de idx/N",
                # que empilhava várias palavras da letra na mesma).
                for w in match_words_in_order(official_words, words):
                    lyrics_timed.append({
                        "word": w["word"],
                        "expected_start": round(max(0.0, w["start"]), 3),
                        "expected_end": round(max(0.0, w["end"]), 3),
                    })
        else:
            # Fallback completo se o Whisper falhar: distribui uniformemente no tempo do segmento extraído
            max_duration = segment_audio.size / sample_rate
            n_off = len(official_words)
            for idx, off_word in enumerate(official_words):
                ratio = idx / n_off
                t_start = ratio * max_duration
                t_end = min(t_start + 0.3, max_duration)
                lyrics_timed.append({
                    "word": off_word,
                    "expected_start": round(t_start, 3),
                    "expected_end": round(t_end, 3)
                })
        
        # Garante que:
        # 1. Nenhuma palavra tenha expected_start menor que 0.05s
        # 2. Os tempos expected_start sejam estritamente crescentes (monotônicos com delta de 50ms)
        #    para evitar que palavras posteriores acendam antes de palavras anteriores no frontend!
        # Ajustar o voice_delay para dar um respiro (margem inicial de 400ms) antes do início do canto
        voice_delay = max(0.0, words[0]["start"] - 0.4) if words else 0.0
        if words:
            for w in lyrics_timed:
                w["expected_start"] = max(0.0, round(w["expected_start"] - voice_delay, 3))
                w["expected_end"] = max(0.0, round(w["expected_end"] - voice_delay, 3))

        # 2. Garante mínimo de 0.05 na primeira palavra e monotônico
        if lyrics_timed:
            lyrics_timed[0]["expected_start"] = max(0.05, lyrics_timed[0]["expected_start"])
            if lyrics_timed[0]["expected_end"] < lyrics_timed[0]["expected_start"] + 0.1:
                lyrics_timed[0]["expected_end"] = round(lyrics_timed[0]["expected_start"] + 0.1, 3)
                
            for idx in range(1, len(lyrics_timed)):
                min_start = round(lyrics_timed[idx - 1]["expected_start"] + 0.05, 3)
                if lyrics_timed[idx]["expected_start"] < min_start:
                    lyrics_timed[idx]["expected_start"] = min_start
                if lyrics_timed[idx]["expected_end"] < lyrics_timed[idx]["expected_start"] + 0.1:
                    lyrics_timed[idx]["expected_end"] = round(lyrics_timed[idx]["expected_start"] + 0.1, 3)

        total_duration = len(full_audio) / sample_rate
        max_end = end_sample / sample_rate
        if words:
            actual_sing_end = line["start"] + words[-1]["end"]
            if line.get("end") is not None:
                sing_end = min(actual_sing_end + 0.4, line["end"])
            else:
                sing_end = min(actual_sing_end + 0.4, total_duration)
            pause_end = min(sing_end + 0.1, total_duration)
        else:
            sing_end = min(max_end, total_duration)
            pause_end = min(sing_end + 0.5, total_duration)

        # --- Correção de subestimação do Whisper (somente versos com gap explícito) ---
        # Sintoma: o Whisper só "ouve" um fragmento da voz (ex.: nota sustentada longa),
        # devolve menos palavras que a letra, e o alinhamento por proximidade colapsa todas
        # as palavras no início, com sing_end curtíssimo — apesar de o LRC reservar muito
        # mais tempo para o verso.
        #
        # Gates de segurança (os três precisam ser verdadeiros) para nunca interferir nos
        # casos corretos:
        #   1. line["end"] existe -> verso seguido de pausa instrumental. Versos com letra
        #      logo em seguida têm line["end"] == None e jamais entram aqui.
        #   2. A contagem do Whisper diverge da letra -> o ramo de match 1:1 perfeito
        #      (alinhamento confiável) nunca é tocado.
        #   3. O trecho de voz detectado cobre menos da metade do tempo do LRC e sobram
        #      mais de 2s "perdidos" -> só subestimações grosseiras disparam.
        lrc_end = line.get("end")
        if (
            lrc_end is not None
            and words
            and lyrics_timed
            and len(regroup_timed_words(words, language)) != len(official_words)
        ):
            lrc_duration = lrc_end - line["start"]
            detected_span = words[-1]["end"]  # relativo ao início do segmento
            if detected_span < 0.5 * lrc_duration and (lrc_duration - detected_span) > 2.0:
                n = len(lyrics_timed)
                usable = max(0.0, lrc_duration - 0.2)  # margem de respiro no fim
                slice_dur = usable / n if n else usable
                for idx in range(n):
                    w_start = round(0.05 + idx * slice_dur, 3)
                    w_end = round(min(0.05 + (idx + 1) * slice_dur, usable), 3)
                    lyrics_timed[idx]["expected_start"] = w_start
                    lyrics_timed[idx]["expected_end"] = w_end
                sing_end = lrc_end
                pause_end = min(sing_end + 0.1, total_duration)
                voice_delay = 0.0  # distribuímos a partir do início real do verso (LRC)
                print(
                    f"  -> Subestimacao do Whisper detectada: redistribuindo {n} "
                    f"palavras em {lrc_duration:.2f}s do LRC (voz detectada: "
                    f"{detected_span:.2f}s)"
                )

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

    # sing_end cobre a última palavra e não invade o verso seguinte
    finalize_segments(segments_data, len(full_audio) / sample_rate + offset)

    # Salvar segments.json
    if debug:
        output_path = song_path / "segments_debug.json"
    else:
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
