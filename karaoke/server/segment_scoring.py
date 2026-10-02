"""Nota de um verso a partir do áudio recortado: compartilhado pelo servidor e
pelo `tools/replay_recording.py`, para a repetição de uma gravação pontuar
exatamente como o jogo ao vivo."""
from __future__ import annotations

import re

from lyrics_text import (
    has_japanese_script, is_japanese, lead_words, project_onto_romaji_lyrics, regroup_timed_words,
    split_words, strip_backing,
)
from score_engine import calculate_score

# Trechos não-lexicais que pulam o Whisper e são pontuados só por energia (RMS).
VOCALIZE_WORDS = {
    "oh", "la", "uh", "na", "ah", "oo", "woo", "yeah", "yeh", "wow",
    "hm", "hmm", "hey", "hei",
}
VOCALIZE_HIGH_RMS = 0.008
VOCALIZE_LOW_RMS = 0.002
# Abaixo disso o verso é silêncio e nem vai para o Whisper.
SILENCE_RMS = 0.0018


def is_vocalize(seg_text: str) -> bool:
    clean_words = [re.sub(r"[^\w]", "", w.lower()) for w in seg_text.split()]
    return len(clean_words) > 0 and all(w in VOCALIZE_WORDS for w in clean_words if w)


def score_vocalize(seg_text: str, rms: float) -> tuple[float, str, int, int]:
    """Pontua segmentos não-lexicais (oh-oh, la-la-la) só pela energia."""
    clean_words = [re.sub(r"[^\w]", "", w.lower()) for w in seg_text.split()]
    total = len(clean_words)
    if rms > VOCALIZE_HIGH_RMS:
        return 100.0, seg_text, total, total
    if rms > VOCALIZE_LOW_RMS:
        return 50.0, "(som baixo)", total // 2, total
    return 0.0, "(silêncio)", 0, total


def shift_words(words: list[dict], offset: float) -> list[dict]:
    """Converte tempos relativos ao início da janela para relativos ao sing_start."""
    return [{**w, "start": w["start"] + offset, "end": w["end"] + offset} for w in words]


def needs_whisper(segment: dict, rms: float) -> bool:
    return not is_vocalize(segment["lyrics"]) and rms >= SILENCE_RMS


def score_whisper_free(segment: dict, rms: float) -> dict:
    """Verso de vocalize (nota por energia) ou silencioso (nota 0)."""
    if is_vocalize(segment["lyrics"]):
        score, transcription, matched, total = score_vocalize(segment["lyrics"], rms)
        return {"score": score, "transcription": transcription, "matched_words": matched, "total_expected": total}
    return {"score": 0.0, "transcription": "", "matched_words": 0, "total_expected": len(lead_words(segment["lyrics_timed"]))}


def transcribe_kwargs(segment: dict) -> dict:
    """Argumentos do STTEngine.transcribe para o verso (sem o áudio).

    A voz de apoio (entre parênteses) fica fora: o cantor não a canta."""
    expected = [w["word"] for w in lead_words(segment["lyrics_timed"] or [])] or None
    prompt = strip_backing(segment["lyrics"]) or segment["lyrics"]
    return {"language": segment["language"], "initial_prompt": prompt, "expected_words": expected}


def score_words(segment: dict, prev_segment: dict | None, words: list[dict], scoring_mode: str) -> dict:
    """Nota das palavras do Whisper, já com tempos relativos ao sing_start."""
    language = segment["language"]
    prev_lyrics = split_words(prev_segment["lyrics"], language) if prev_segment else None
    if is_japanese(language) and not has_japanese_script(segment["lyrics"]):
        # Letra colada em romaji e o Whisper escreve em kana: compara pela pronúncia,
        # projetando o que foi ouvido sobre as palavras da letra.
        words = project_onto_romaji_lyrics(words, segment["lyrics"])
    else:
        # Japonês: o Whisper devolve pedaços de 1–3 caracteres; regrupa nas unidades da letra.
        words = regroup_timed_words(words, language)
    return calculate_score(
        lead_words(segment["lyrics_timed"]), words,
        prev_expected_words=prev_lyrics, language=segment["language"], scoring_mode=scoring_mode,
    )
