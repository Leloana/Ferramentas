"""Tempos das palavras e dos versos do segments.json (usado pelo prepare_song).

Duas correções de alinhamento que eram fonte de letra "grudada" ou cortada:

- `match_words_in_order`: quando o Whisper devolve um número de palavras
  diferente da letra, cada palavra da letra ia para a palavra do Whisper mais
  próxima de `idx/N × duração`. Várias caíam na mesma e o ajuste monotônico
  as empilhava a 50 ms uma da outra. Agora é um casamento que respeita a
  ordem (programação dinâmica por semelhança) e as palavras sem par são
  interpoladas entre as âncoras pelo número de sílabas.
- `finalize_segments`: `sing_end` não passava da última palavra (a TV para de
  acender em `sing_end`) e podia invadir o verso seguinte (a janela de áudio
  do próximo verso começava depois, cortando a 1ª palavra dele da nota).
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz
from unidecode import unidecode

from utils.lrc_realign import interpolate_missing_words

MATCH_MIN_SIMILARITY = 0.6
VERSE_GAP_SEC = 0.02
END_AFTER_LAST_WORD_SEC = 0.05


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", unidecode(word).lower())


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.ratio(a, b) / 100.0


def match_words_in_order(official_words: list[str], whisper_words: list[dict]) -> list[dict]:
    """Casa a letra com as palavras do Whisper sem inverter a ordem.

    Devolve [{"word", "start", "end"}] com um item por palavra da letra, tempos
    relativos ao mesmo zero das palavras do Whisper.
    """
    n, m = len(official_words), len(whisper_words)
    ref = [_norm(w) for w in official_words]
    hyp = [_norm(w.get("word", "")) for w in whisper_words]

    # best[i][j]: maior soma de semelhanças casando ref[:i] com hyp[:j]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        row, prev = best[i], best[i - 1]
        for j in range(1, m + 1):
            score = max(prev[j], row[j - 1])
            sim = _similarity(ref[i - 1], hyp[j - 1])
            if sim >= MATCH_MIN_SIMILARITY:
                score = max(score, prev[j - 1] + sim)
            row[j] = score

    pairs = {}
    i, j = n, m
    while i > 0 and j > 0:
        sim = _similarity(ref[i - 1], hyp[j - 1])
        if sim >= MATCH_MIN_SIMILARITY and abs(best[i][j] - (best[i - 1][j - 1] + sim)) < 1e-9:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif best[i][j] == best[i - 1][j]:
            i -= 1
        else:
            j -= 1

    out = []
    for k, word in enumerate(official_words):
        if k in pairs:
            w = whisper_words[pairs[k]]
            out.append({"word": word, "start": float(w["start"]), "end": float(w["end"])})
        else:
            out.append({"word": word, "start": None, "end": None})

    if not pairs:
        # nada casou: mantém a ordem do Whisper como guia de ritmo, se houver
        if whisper_words:
            first = float(whisper_words[0]["start"])
            last = float(whisper_words[-1]["end"])
            step = max(0.15, (last - first) / max(1, n))
            for k, item in enumerate(out):
                item["start"] = first + k * step
                item["end"] = item["start"] + step * 0.9
            return out
    return interpolate_missing_words(out)


def has_lyrics(text) -> bool:
    """Verso de verdade tem letra ou número; "♪", "♫", "*" etc. marcam trecho instrumental."""
    return any(ch.isalnum() for ch in str(text or ""))


def finalize_segments(segments: list[dict], total_duration: float | None = None) -> list[dict]:
    """Ajusta sing_end/pausas: cobre a última palavra e não invade o próximo verso.

    Tira da lista (no lugar: há quem ignore o retorno) os "versos" sem letra, como
    o "♪" das letras do LRCLIB — viravam 1,7 s de canto pontuado no instrumental.
    """
    segments[:] = [seg for seg in segments if "lyrics" not in seg or has_lyrics(seg["lyrics"])]
    for idx, seg in enumerate(segments):
        start = seg["sing_start"]
        words = seg.get("lyrics_timed") or []
        end = seg["sing_end"]
        if words:
            last_word_end = start + max(w["expected_end"] for w in words)
            end = max(end, last_word_end + END_AFTER_LAST_WORD_SEC)

        nxt = segments[idx + 1] if idx + 1 < len(segments) else None
        if nxt is not None:
            end = min(end, nxt["sing_start"] - VERSE_GAP_SEC)
        if total_duration is not None:
            end = min(end, total_duration)
        end = max(end, start + 0.1)

        # nenhuma palavra termina depois do verso
        limit = end - start
        for w in words:
            if w["expected_end"] > limit:
                w["expected_end"] = round(max(w["expected_start"] + 0.05, limit), 3)

        seg["sing_end"] = round(end, 3)
        seg["pause_start"] = seg["sing_end"]
        pause_end = max(seg.get("pause_end", end), seg["sing_end"])
        if nxt is not None:
            pause_end = min(pause_end, nxt["sing_start"])
        seg["pause_end"] = round(max(pause_end, seg["sing_end"]), 3)
    return segments
