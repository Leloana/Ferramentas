"""Utilitário de realinhamento de segmentos LRC.

Este módulo contém funções puras para realinhar segmentos JSON gerados pelo Whisper
com a letra de referência real (texto puro) e gerar o LRC final.
Utiliza alinhamento word-level global, similaridade fonética (Metaphone) e interpolação silábica.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from rapidfuzz import fuzz
from metaphone import doublemetaphone
from unidecode import unidecode

logger = logging.getLogger(__name__)


def _normalize_word(w: str) -> str:
    """Lowercase, unidecode e remove pontuação. Retorna vazio se não sobrou nada."""
    cleaned = re.sub(r"[^\w]", "", unidecode(w).lower())
    return cleaned


def phonetic_similarity(a: str, b: str) -> float:
    """Calcula similaridade fonética usando Double Metaphone."""
    if not a or not b:
        return 0.0
    ma = doublemetaphone(a)
    mb = doublemetaphone(b)
    score = 0.0
    for code_a in ma:
        for code_b in mb:
            if code_a and code_b:
                s = fuzz.ratio(code_a, code_b)
                if s > score:
                    score = s
    return score


def get_hybrid_score(ref_word: str, wh_word: str) -> float:
    """Score híbrido: 50% léxico (híbrido token_set e ratio) e 50% fonético."""
    if not ref_word or not wh_word:
        return 0.0
    lexical = 0.7 * fuzz.token_set_ratio(ref_word, wh_word) + 0.3 * fuzz.ratio(ref_word, wh_word)
    phonetic = phonetic_similarity(ref_word, wh_word)
    return 0.5 * lexical + 0.5 * phonetic


def get_threshold(word: str) -> float:
    """Threshold adaptativo baseado no tamanho da palavra."""
    l = len(word)
    if l <= 3:
        return 95.0
    elif l <= 5:
        return 85.0
    else:
        return 75.0


def get_contextual_score(ref_tokens: list[str], wh_tokens: list[str], ref_idx: int, wh_idx: int) -> float:
    """Score contextual: avalia a palavra atual e seus vizinhos."""
    score = get_hybrid_score(ref_tokens[ref_idx], wh_tokens[wh_idx])
    
    # prev word
    if ref_idx > 0 and wh_idx > 0:
        score += 0.2 * get_hybrid_score(ref_tokens[ref_idx-1], wh_tokens[wh_idx-1])
    # next word
    if ref_idx < len(ref_tokens) - 1 and wh_idx < len(wh_tokens) - 1:
        score += 0.2 * get_hybrid_score(ref_tokens[ref_idx+1], wh_tokens[wh_idx+1])
        
    return score


def count_syllables(word: str) -> int:
    """Estimativa de sílabas para interpolação ponderada."""
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    if not word:
        return 1
    if word[0] in vowels:
        count += 1
    for index in range(1, len(word)):
        if word[index] in vowels and word[index - 1] not in vowels:
            count += 1
    if word.endswith("e"):
        count -= 1
    if count == 0:
        count += 1
    return count


def interpolate_missing_words(word_objs: list[dict]) -> list[dict]:
    """Preenche tempos None usando interpolação ponderada por sílabas."""
    n = len(word_objs)
    if n == 0:
        return word_objs
    
    anchors = [i for i, w in enumerate(word_objs) if w["start"] is not None]
    if not anchors:
        # Fallback total: espalha linearmente com 400ms por palavra
        t = 0.0
        for w in word_objs:
            w["start"] = t
            w["end"] = t + 0.3
            t += 0.4
        return word_objs

    # Estima taxa vocal média nas bordas
    if len(anchors) >= 2:
        a0, a1 = anchors[0], anchors[1]
        rate_start = (word_objs[a1]["start"] - word_objs[a0]["start"]) / max(1, a1 - a0)
        rate_start = max(0.15, min(rate_start, 1.0))
        am1, am2 = anchors[-1], anchors[-2]
        rate_end = (word_objs[am1]["start"] - word_objs[am2]["start"]) / max(1, am1 - am2)
        rate_end = max(0.15, min(rate_end, 1.0))
    else:
        rate_start = rate_end = 0.4

    # Extrapola antes da primeira âncora
    first = anchors[0]
    for i in range(first - 1, -1, -1):
        prev_start = word_objs[i+1]["start"]
        word_objs[i]["end"] = max(0.0, prev_start - 0.05)
        word_objs[i]["start"] = max(0.0, word_objs[i]["end"] - rate_start)

    # Interpola gaps internos
    for a, b in zip(anchors, anchors[1:]):
        if b - a > 1:
            gap_start = word_objs[a]["end"]
            if gap_start is None:
                gap_start = word_objs[a]["start"] + 0.3
            gap_end = word_objs[b]["start"]
            
            if gap_end < gap_start + 0.1:
                gap_start = max(0.0, gap_end - 0.1)
                
            total_syllables = sum(count_syllables(word_objs[k]["word"]) for k in range(a + 1, b))
            current_t = gap_start
            
            for k in range(a + 1, b):
                syllables = count_syllables(word_objs[k]["word"])
                ratio = syllables / max(1, total_syllables)
                duration = (gap_end - gap_start) * ratio
                word_objs[k]["start"] = current_t
                word_objs[k]["end"] = current_t + duration * 0.9
                current_t += duration

    # Extrapola após a última âncora
    last = anchors[-1]
    for i in range(last + 1, n):
        prev_end = word_objs[i-1]["end"]
        if prev_end is None:
            prev_end = word_objs[i-1]["start"] + 0.3
        word_objs[i]["start"] = prev_end + 0.05
        word_objs[i]["end"] = word_objs[i]["start"] + rate_end

    return word_objs


def _parse_ref_lines(plain_lyrics: str) -> list[str]:
    """Remove linhas em branco e limpa tags LRC/metadados da letra pura."""
    out = []
    for line in plain_lyrics.splitlines():
        s = line.strip()
        if not s:
            continue
        cleaned = re.sub(r"\[[^\]]*\]", "", s).strip()
        if cleaned:
            out.append(cleaned)
    return out


def _format_timestamp(t: float) -> str:
    """Formata timestamp absoluto em [MM:SS.xx]."""
    m = int(t // 60)
    s = int(t % 60)
    ms = int((t % 1) * 100)
    return f"[{m:02d}:{s:02d}.{ms:02d}]"


def generate_lrc_from_segments(segments: list[dict]) -> str:
    """Gera o texto LRC a partir dos segmentos, injetando pausas longas."""
    out = []
    n = len(segments)
    for i, seg in enumerate(segments):
        start_t = seg["sing_start"]
        lyrics = seg["lyrics"]
        out.append(f"{_format_timestamp(start_t)}{lyrics}")

        end_t = seg["sing_end"]
        next_start = segments[i + 1]["sing_start"] if i + 1 < n else (end_t + 2.0)

        if (next_start - end_t) > 0.6:
            out.append(f"{_format_timestamp(end_t)}")

    return "\n".join(out)


def realign_segments(
    segments: list[dict],
    plain_lyrics: str,
    diagnostics: list[dict] | None = None,
) -> tuple[list[dict], str]:
    """Realinha segmentos com a letra usando o pipeline word-level global.

    Retorna os segmentos corrigidos e o texto LRC gerado.
    """
    real_lines = _parse_ref_lines(plain_lyrics)
    logger.info(f"Processando {len(real_lines)} linhas via alinhamento global word-level (fonético+contextual).")

    # 1. Flatten Whisper streams (âncoras de tempo temporárias)
    wh_words = []
    for seg in segments:
        for w in seg.get("lyrics_timed", []):
            norm = _normalize_word(w["word"])
            if norm:
                start = w.get("expected_start", 0.0)
                wh_words.append({
                    "word": norm,
                    "start": start,
                    "end": w.get("expected_end", start + 0.3)
                })
    
    wh_tokens = [w["word"] for w in wh_words]

    # 2. Flatten Official lyrics
    ref_words_flat = []
    line_indices = []
    for i, line in enumerate(real_lines):
        for raw_word in line.split():
            norm = _normalize_word(raw_word)
            if norm:
                ref_words_flat.append({"raw": raw_word, "norm": norm})
                line_indices.append(i)
                
    ref_tokens = [w["norm"] for w in ref_words_flat]

    # 3. Matching Monotônico Contextual
    cursor = 0
    matched_wh = [None] * len(ref_tokens)
    
    for i, ref_word in enumerate(ref_tokens):
        best_score = 0
        best_j = -1
        threshold = get_threshold(ref_word)
        
        # Otimização: buscar numa janela próxima ao cursor
        window_end = min(len(wh_tokens), cursor + 40)
        for j in range(cursor, window_end):
            score = get_contextual_score(ref_tokens, wh_tokens, i, j)
            if score > best_score:
                best_score = score
                best_j = j
                
        # Nunca paramos no primeiro: avaliamos a janela inteira e pegamos o best_j
        if best_j != -1 and best_score >= threshold:
            matched_wh[i] = wh_words[best_j]
            cursor = best_j + 1  # Avança cursor para forçar monotonicidade temporal

    # 4. Interpolação Global de Buracos
    global_word_objs = []
    matched_count = 0
    for k in range(len(ref_tokens)):
        raw = ref_words_flat[k]["raw"]
        match = matched_wh[k]
        if match:
            global_word_objs.append({"word": raw, "start": match["start"], "end": match["end"]})
            matched_count += 1
        else:
            global_word_objs.append({"word": raw, "start": None, "end": None})
            
    logger.info(f"Matched {matched_count}/{len(ref_tokens)} palavras globais com suporte fonético.")
    global_word_objs = interpolate_missing_words(global_word_objs)

    # 5. Reconstrução Bottom-Up das Linhas (Split e Merge Natural)
    corrected_segments = []
    
    for i, line_text in enumerate(real_lines):
        indices = [k for k, li in enumerate(line_indices) if li == i]
        if not indices:
            continue
        
        sub_lyrics_timed = []
        for k in indices:
            sub_lyrics_timed.append({
                "word": global_word_objs[k]["word"],
                "expected_start": round(global_word_objs[k]["start"], 3),
                "expected_end": round(global_word_objs[k]["end"], 3)
            })
            
        sing_start = sub_lyrics_timed[0]["expected_start"]
        sing_end = sub_lyrics_timed[-1]["expected_end"]
        
        # Preserva pausas naturais detectadas pelo word-level
        pause_start = sing_end
        pause_end = sing_end + 0.1
        
        # Merge natural: a linha oficial é a lei, o whisper apenas fornece as âncoras.
        seg = {
            "id": i + 1,
            "label": f"Parte {i + 1}",
            "sing_start": round(sing_start, 3),
            "sing_end": round(sing_end, 3),
            "pause_start": round(pause_start, 3),
            "pause_end": round(pause_end, 3),
            "lyrics": line_text,
            "lyrics_timed": sub_lyrics_timed
        }
        if segments and "language" in segments[0]:
            seg["language"] = segments[0]["language"]
            
        corrected_segments.append(seg)
        
        if diagnostics is not None:
            # Identifica quantas palavras desta linha foram ancoradas de verdade
            line_matched = sum(1 for k in indices if matched_wh[k] is not None)
            diagnostics.append({
                "original_id": i + 1,
                "original_lyrics": line_text,
                "matched_lines_count": line_matched,
                "total_words": len(indices),
                "split_happened": False,
                "sub_segments": []
            })

    # Gera LRC final
    lrc_text = generate_lrc_from_segments(corrected_segments)

    return corrected_segments, lrc_text


def test_realign(segments_path: str, lyrics_path: str) -> None:
    """Testa o novo fluxo global word-level e imprime diagnósticos."""
    with open(segments_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
    with open(lyrics_path, "r", encoding="utf-8") as f:
        plain_lyrics = f.read()

    diagnostics = []
    corrected_segments, lrc_text = realign_segments(segments, plain_lyrics, diagnostics=diagnostics)

    print("=== LRC GERADO ===")
    print(lrc_text)
    print("\n" + "="*50)
    print("=== RELATÓRIO DE DIAGNÓSTICO (GLOBAL WORD-LEVEL) ===")
    print("="*50)

    for diag in diagnostics:
        orig_id = diag["original_id"]
        orig_lyrics = diag["original_lyrics"]
        matched_count = diag.get("matched_lines_count", 0)
        total = diag.get("total_words", 0)

        print(f"Linha Oficial {orig_id:02d} ('{orig_lyrics}') -> {matched_count}/{total} palavras ancoradas via Whisper")
        print("-" * 50)
