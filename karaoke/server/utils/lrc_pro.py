"""Alinhamento Forçado Dedicado (Forced Alignment) usando torchaudio.pipelines.MMS_FA.

Este módulo implementa o alinhamento preciso de letras de música com áudio vocal,
garantindo que cada verso e palavra respeitem rigorosamente a letra de referência,
mesmo sem pausas ou silêncios detectáveis (VAD).
"""

import re
import logging
import torch
import torchaudio
import torchaudio.functional as F
from pathlib import Path
from unidecode import unidecode

logger = logging.getLogger(__name__)


def _format_timestamp(t: float) -> str:
    """Formata timestamp absoluto em [MM:SS.xx]."""
    m = int(t // 60)
    s = int(t % 60)
    ms = int((t % 1) * 100)
    return f"[{m:02d}:{s:02d}.{ms:02d}]"


def parse_and_normalize_lyrics(plain_lyrics: str) -> tuple[list[list[dict]], list[str]]:
    """
    Divide a letra plana em linhas e palavras.
    Retorna:
      - lines: lista de linhas, onde cada linha é uma lista de dicionários de palavras.
      - flat_normalized_words: lista plana de palavras normalizadas não-vazias para o tokenizer.
    """
    lines = []
    flat_normalized_words = []
    
    for line in plain_lyrics.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ignora tags LRC de metadados
        if line.startswith("[") and "]" in line:
            if ":" in line or line.lower().startswith("[offset"):
                continue
        
        words_in_line = []
        for raw_word in line.split():
            # Normalização fonética/alfabética compatível com MMS_FA vocabulary:
            # remove acentos, converte para minúsculas e mantém apenas a-z e '
            norm_word = unidecode(raw_word).lower()
            norm_word = re.sub(r"[^a-z']", "", norm_word)
            
            word_dict = {
                "raw": raw_word,
                "norm": norm_word,
                "start": None,
                "end": None
            }
            words_in_line.append(word_dict)
            if norm_word:
                flat_normalized_words.append(norm_word)
                
        if words_in_line:
            lines.append(words_in_line)
            
    return lines, flat_normalized_words


def align_lyrics_forced(
    vocal_audio_path: str,
    plain_lyrics: str,
    language: str = "pt",
    device: str = None
) -> tuple[list[dict], str]:
    """
    Realiza o alinhamento forçado (Forced Alignment) usando MMS_FA.
    
    Retorna:
      - corrected_segments: Lista de segmentos em formato JSON compatível com frontend.
      - lrc_text: O arquivo LRC final correspondente aos timestamps gerados.
    """
    # 1. Carregar áudio
    logger.info(f"Carregando áudio vocal para alinhamento forçado: {vocal_audio_path}")
    waveform, sample_rate = torchaudio.load(vocal_audio_path)
    
    # 2. Converter para Mono se necessário
    if waveform.size(0) > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
        
    # 3. Resampling para 16kHz se necessário
    if sample_rate != 16000:
        waveform = F.resample(waveform, sample_rate, 16000)
        sample_rate = 16000
        
    audio_duration_sec = waveform.size(1) / sample_rate
    
    # 4. Auto-detectar dispositivo
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)
    logger.info(f"Executando Forced Alignment no dispositivo: {device}")
    
    # 5. Inicializar o pipeline MMS_FA e computar alinhamento com try-finally para evitar vazamento de VRAM
    model = None
    emission = None
    token_spans = None
    waveform_cuda = None
    
    try:
        bundle = torchaudio.pipelines.MMS_FA
        model = bundle.get_model().to(device)
        tokenizer = bundle.get_tokenizer()
        aligner = bundle.get_aligner()
        
        # 6. Normalizar a letra
        lines, flat_normalized_words = parse_and_normalize_lyrics(plain_lyrics)
        if not flat_normalized_words:
            raise ValueError("A letra fornecida não contém palavras válidas para alinhamento.")
            
        # 7. Tokenizar a letra normalizada
        tokens = tokenizer(flat_normalized_words)
        
        # 8. Computar emissões e alinhamento
        waveform_cuda = waveform.to(device)
        with torch.inference_mode():
            emission, _ = model(waveform_cuda)
            # O aligner espera uma emissão 2D (time, tokens)
            token_spans = aligner(emission[0], tokens)
            
        num_frames = emission.size(1)
        ratio = audio_duration_sec / num_frames
        
        # 9. Mapear spans de volta para as palavras da letra
        span_idx = 0
        for line in lines:
            for word in line:
                if word["norm"] and span_idx < len(token_spans):
                    spans = token_spans[span_idx]
                    span_idx += 1
                    if spans:
                        # Converte de índice de frame para segundos
                        word["start"] = round(spans[0].start * ratio, 3)
                        word["end"] = round(spans[-1].end * ratio, 3)
                        
        # 10. Interpolação para palavras órfãs ou não casadas
        # Prepara lista achatada para a função de interpolação do lrc_realign
        flat_words_for_interpolation = []
        for line in lines:
            for word in line:
                flat_words_for_interpolation.append({
                    "word": word["raw"],
                    "start": word["start"],
                    "end": word["end"]
                })
                
        try:
            from utils.lrc_realign import interpolate_missing_words
            interpolated = interpolate_missing_words(flat_words_for_interpolation)
            
            # Mapeia de volta os tempos interpolados
            idx = 0
            for line in lines:
                for word in line:
                    word["start"] = interpolated[idx]["start"]
                    word["end"] = interpolated[idx]["end"]
                    idx += 1
        except Exception as e:
            logger.warning(f"Erro ao importar ou executar interpolate_missing_words do lrc_realign: {e}. Executando interpolação local fallback.")
            # Fallback local simples se não puder importar
            t = 0.0
            for word in flat_words_for_interpolation:
                if word["start"] is None:
                    word["start"] = t
                    word["end"] = t + 0.3
                t = word["end"] + 0.1
                
            idx = 0
            for line in lines:
                for word in line:
                    word["start"] = flat_words_for_interpolation[idx]["start"]
                    word["end"] = flat_words_for_interpolation[idx]["end"]
                    idx += 1
                    
        # 11. Construir segmentos de versos (lines) para o frontend
        corrected_segments = []
        num_lines = len(lines)
        for i, line_words in enumerate(lines):
            line_text = " ".join([w["raw"] for w in line_words])
            
            # Tempos absolutos das palavras
            first_word_start = line_words[0]["start"]
            last_word_end = line_words[-1]["end"]
            
            # Limite superior do final do canto (início da próxima linha de letra ou fim do áudio)
            next_word_start = lines[i + 1][0]["start"] if i + 1 < num_lines else audio_duration_sec
            
            # sing_start com margem vocal de 400ms se possível (não menor que zero e não sobrepondo a palavra anterior)
            # Se for o primeiro verso, pode ir até 0.
            prev_word_end = lines[i - 1][-1]["end"] if i > 0 else 0.0
            sing_start = max(prev_word_end, first_word_start - 0.4)
            
            # sing_end com margem de 400ms pós-nota se possível (não passando da primeira palavra do próximo verso)
            sing_end = min(last_word_end + 0.4, next_word_start)
            
            # Corrige caso por algum motivo sing_start seja maior ou igual a sing_end
            if sing_start >= sing_end:
                sing_start = max(0.0, first_word_start - 0.05)
                sing_end = min(last_word_end + 0.05, next_word_start)
                
            sub_lyrics_timed = []
            for word in line_words:
                # O frontend espera tempos relativos ao início do segmento (sing_start)
                sub_lyrics_timed.append({
                    "word": word["raw"],
                    "expected_start": round(max(0.0, word["start"] - sing_start), 3),
                    "expected_end": round(max(0.0, word["end"] - sing_start), 3)
                })
                
            # Garante as regras de monotonicidade, tempo mínimo inicial e duração mínima
            if sub_lyrics_timed:
                sub_lyrics_timed[0]["expected_start"] = max(0.05, sub_lyrics_timed[0]["expected_start"])
                if sub_lyrics_timed[0]["expected_end"] < sub_lyrics_timed[0]["expected_start"] + 0.1:
                    sub_lyrics_timed[0]["expected_end"] = round(sub_lyrics_timed[0]["expected_start"] + 0.1, 3)
                    
                for idx in range(1, len(sub_lyrics_timed)):
                    min_start = round(sub_lyrics_timed[idx - 1]["expected_start"] + 0.05, 3)
                    if sub_lyrics_timed[idx]["expected_start"] < min_start:
                        sub_lyrics_timed[idx]["expected_start"] = min_start
                    if sub_lyrics_timed[idx]["expected_end"] < sub_lyrics_timed[idx]["expected_start"] + 0.1:
                        sub_lyrics_timed[idx]["expected_end"] = round(sub_lyrics_timed[idx]["expected_start"] + 0.1, 3)
                        
            # Pausa natural
            pause_start = sing_end
            pause_end = min(sing_end + 0.1, next_word_start)
            
            seg = {
                "id": i + 1,
                "label": f"Parte {i + 1}",
                "sing_start": round(sing_start, 3),
                "sing_end": round(sing_end, 3),
                "pause_start": round(pause_start, 3),
                "pause_end": round(pause_end, 3),
                "language": language,
                "lyrics": line_text,
                "lyrics_timed": sub_lyrics_timed
            }
            corrected_segments.append(seg)
            
        # 12. Gerar LRC final
        lrc_lines = []
        n = len(corrected_segments)
        for i, seg in enumerate(corrected_segments):
            start_t = seg["sing_start"]
            lyrics = seg["lyrics"]
            lrc_lines.append(f"{_format_timestamp(start_t)}{lyrics}")
            
            end_t = seg["sing_end"]
            next_start = corrected_segments[i + 1]["sing_start"] if i + 1 < n else (end_t + 2.0)
            
            # Injeta tag de pausa silenciosa se houver espaço suficiente
            if (next_start - end_t) > 0.6:
                lrc_lines.append(f"{_format_timestamp(end_t)}")
                
        lrc_text = "\n".join(lrc_lines)
        
        return corrected_segments, lrc_text

    finally:
        # Liberar memória de GPU proativamente para evitar vazamentos de VRAM no Windows
        logger.info("Limpando recursos e cache da GPU (Forced Alignment)...")
        import gc
        if model is not None:
            del model
        if emission is not None:
            del emission
        if token_spans is not None:
            del token_spans
        if waveform_cuda is not None:
            del waveform_cuda
        if 'waveform' in locals():
            del waveform
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
