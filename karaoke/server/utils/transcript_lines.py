"""Versos de karaokê a partir dos trechos do Whisper (letra gerada sem LRC).

O Whisper devolve trechos do tamanho que quiser: em rap, um trecho de 50 s com
150 palavras. E juntar trechos separados por menos de 0,8 s de silêncio (para
não sobrar fragmento) colava a música toda, porque rap quase não tem pausa
("Rap do Obito": 10 versos, um de 52 s). Aqui um trecho longo é quebrado pelos
tempos das palavras, em pausa ou pontuação, e só trecho curto é juntado.
"""
from __future__ import annotations

# verso cantável: corta acima disso
MAX_LINE_SEC = 7.0
MAX_LINE_WORDS = 12
# corte "natural": pausa entre palavras, ou pontuação depois de palavras suficientes
PAUSE_SEC = 0.5
MIN_WORDS_BEFORE_PUNCT = 4
# juntar dois trechos vizinhos só se o resultado ainda for um verso curto
MERGE_GAP_SEC = 0.8
MERGE_MAX_WORDS = 8
MERGE_MAX_SEC = 5.0

_PUNCT = (",", ".", "!", "?", ";", ":", "、", "。", "！", "？")


def _line(words: list[dict]) -> dict:
    return {"start": float(words[0]["start"]), "end": float(words[-1]["end"]),
            "text": " ".join(w["word"].strip() for w in words if w["word"].strip()),
            "words": words}


def _split(seg: dict) -> list[dict]:
    """Um trecho do Whisper em versos de até MAX_LINE_SEC / MAX_LINE_WORDS."""
    words = [w for w in seg.get("words") or [] if str(w.get("word", "")).strip()]
    n_words = len(seg["text"].split())
    if not words or (seg["end"] - seg["start"] <= MAX_LINE_SEC and n_words <= MAX_LINE_WORDS):
        return [{"start": seg["start"], "end": seg["end"], "text": seg["text"], "words": words}]
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            break
        dur = float(w["end"]) - float(cur[0]["start"])
        pause = float(nxt["start"]) - float(w["end"])
        natural = pause >= PAUSE_SEC or (len(cur) >= MIN_WORDS_BEFORE_PUNCT and w["word"].strip().endswith(_PUNCT))
        if natural or len(cur) >= MAX_LINE_WORDS or dur >= MAX_LINE_SEC:
            out.append(_line(cur))
            cur = []
    if cur:
        out.append(_line(cur))
    return out


def segments_to_lines(segments: list[dict]) -> list[dict]:
    """[{"start", "end", "text", "words"?}] do Whisper → versos {"start", "end", "text"}."""
    lines: list[dict] = []
    for seg in segments:
        if not seg.get("text", "").strip():
            continue
        lines.extend(_split(seg))
    merged: list[dict] = []
    for ln in lines:
        prev = merged[-1] if merged else None
        if prev and ln["start"] - prev["end"] < MERGE_GAP_SEC \
                and len((prev["text"] + " " + ln["text"]).split()) <= MERGE_MAX_WORDS \
                and ln["end"] - prev["start"] <= MERGE_MAX_SEC:
            prev["text"] += " " + ln["text"]
            prev["end"] = ln["end"]
        else:
            merged.append({"start": ln["start"], "end": ln["end"], "text": ln["text"]})
    return merged
