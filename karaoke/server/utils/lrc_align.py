"""Alinha uma letra plana (texto puro, sem timestamps) com a saída do Whisper para gerar LRC.

Função pura: recebe a letra do usuário e os segments do faster-whisper,
devolve o texto LRC final e uma flag indicando se caiu no fallback linear.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

MIN_MATCH_RATIO = 0.70
MIN_FALLBACK_MATCH_PCT = 0.15
MIN_FALLBACK_MATCHES = 3
WHISPER_SEARCH_WINDOW = 12
LINEAR_FALLBACK_END_OFFSET = 5.0
LINEAR_FALLBACK_MIN_SPAN = 10.0
NO_LRC_LINE_INTERVAL_SEC = 4.0  # usado quando o Whisper não devolveu segmentos


def _format_timestamp(t: float) -> str:
    m = int(t // 60)
    s = int(t % 60)
    ms = int((t % 1) * 100)
    return f"[{m:02d}:{s:02d}.{ms:02d}]"


def _parse_ref_lines(plain_lyrics: str) -> list[str]:
    """Remove linhas em branco e diretivas LRC ([tag:...]) do texto do usuário."""
    out = []
    for line in plain_lyrics.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") and "]" in s:
            continue
        out.append(s)
    return out


def _substring_match_ratio(ref_line: str, whisper_text: str) -> float:
    """Fração das palavras de `ref_line` encontradas em `whisper_text` preservando ordem."""
    ref_words = re.findall(r"\b\w+\b", ref_line.lower())
    whisper_words = re.findall(r"\b\w+\b", whisper_text.lower())
    if not ref_words or not whisper_words:
        return 0.0
    matches = 0
    last_idx = -1
    for w in ref_words:
        try:
            idx = whisper_words.index(w, last_idx + 1)
            matches += 1
            last_idx = idx
        except ValueError:
            pass
    return matches / len(ref_words)


def align_plain_lyrics(
    plain_lyrics: str,
    whisper_segments: list,
    title: str,
    artist: str,
    lyrics_start_val: float,
    total_vocal_duration_sec: float,
) -> tuple[str, bool]:
    """Retorna (texto_lrc, fallback_used).

    `whisper_segments` é a sequência de segmentos do `faster_whisper` (cada item
    tem `.start`, `.end`, `.text`). `lyrics_start_val` é o tempo do primeiro
    verso passado pelo usuário (manda no timestamp inicial).
    """
    ref_lines = _parse_ref_lines(plain_lyrics)
    lrc_lines = [f"[ti:{title}]", f"[ar:{artist}]", ""]
    fallback_used = False

    if not ref_lines:
        return "\n".join(lrc_lines), False

    whisper_lines = [
        {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        for seg in whisper_segments
    ]

    if not whisper_lines:
        # Sem nada do Whisper — distribui linearmente a cada N segundos.
        last_t = lyrics_start_val
        for i, ref in enumerate(ref_lines):
            t = last_t + i * NO_LRC_LINE_INTERVAL_SEC
            lrc_lines.append(f"{_format_timestamp(t)}{ref}")
        return "\n".join(lrc_lines), False

    n = len(ref_lines)
    m = len(whisper_lines)
    aligned: list[float | None] = [None] * n
    aligned[0] = lyrics_start_val
    segment_to_ref_lines: dict[int, list[int]] = {}

    # 1. Para cada linha de referência, procura o melhor segmento do Whisper
    #    numa janela deslizante (forward-only) para preservar ordem.
    last_j = 0
    matched_count = 0
    for i in range(n):
        best_j = -1
        best_ratio = 0.0
        for j in range(last_j, min(m, last_j + WHISPER_SEARCH_WINDOW)):
            ratio = _substring_match_ratio(ref_lines[i], whisper_lines[j]["text"])
            if ratio > best_ratio:
                best_ratio = ratio
                best_j = j

        if best_j != -1 and best_ratio >= MIN_MATCH_RATIO:
            aligned[i] = whisper_lines[best_j]["start"]
            last_j = best_j
            matched_count += 1
            segment_to_ref_lines.setdefault(best_j, []).append(i)

    # 2. Se múltiplas refs mapearam pro mesmo segmento, distribui dentro dele.
    for j, indices in segment_to_ref_lines.items():
        if len(indices) > 1:
            seg_start = whisper_lines[j]["start"]
            seg_end = whisper_lines[j]["end"]
            duration = seg_end - seg_start
            for idx, ref_idx in enumerate(indices):
                aligned[ref_idx] = seg_start + idx * (duration / len(indices))

    # 3. Se quase nada bateu, abandona alinhamento e distribui linearmente.
    min_matches_needed = max(MIN_FALLBACK_MATCHES, int(n * MIN_FALLBACK_MATCH_PCT))
    if matched_count < min_matches_needed:
        logger.info(f"Poucos matches com o Whisper ({matched_count}/{n}). Usando distribuição linear robusta.")
        fallback_used = True
        start_t = lyrics_start_val
        end_t = max(start_t + LINEAR_FALLBACK_MIN_SPAN, total_vocal_duration_sec - LINEAR_FALLBACK_END_OFFSET)
        step = (end_t - start_t) / max(1, n - 1)
        for i in range(n):
            aligned[i] = start_t + i * step
    else:
        # 4. Interpolação para preencher gaps; força monotonicidade.
        last_t = lyrics_start_val
        for i in range(n):
            if aligned[i] is None:
                next_t = None
                k = i + 1
                for k in range(i + 1, n):
                    if aligned[k] is not None:
                        next_t = aligned[k]
                        break
                if next_t is not None:
                    steps = (k - i) + 1
                    aligned[i] = last_t + (next_t - last_t) / steps
                else:
                    aligned[i] = last_t + 3.0
            if aligned[i] < last_t:
                aligned[i] = last_t + 0.1
            last_t = aligned[i]

    # 5. Renderiza, forçando o timestamp inicial a `lyrics_start_val` se positivo.
    for i, ref in enumerate(ref_lines):
        t = aligned[i]
        if i == 0 and lyrics_start_val > 0:
            t = lyrics_start_val
        lrc_lines.append(f"{_format_timestamp(t)}{ref}")

    clean_lines = [line.strip() for line in lrc_lines if line.strip()]
    return "\n".join(clean_lines), fallback_used


def draft_lrc_from_whisper(
    whisper_segments: list,
    title: str,
    artist: str,
    lyrics_start_val: float,
) -> str:
    """Gera rascunho LRC direto da saída do Whisper (sem letra de referência)."""
    lrc_lines = [f"[ti:{title}]", f"[ar:{artist}]", ""]
    for i, seg in enumerate(whisper_segments):
        # Whisper às vezes zera o tempo do primeiro vocal — usa o lyrics_start_val.
        shifted_start = lyrics_start_val if (i == 0 and lyrics_start_val > 0) else seg.start
        lrc_lines.append(f"{_format_timestamp(shifted_start)}{seg.text.strip()}")
    return "\n".join(lrc_lines)
