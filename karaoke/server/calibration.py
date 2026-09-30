"""Repontuar partidas gravadas com a nota atual e medir contra o gabarito.

Usado pelos testes das partidas reais (tests/unit/test_recorded_sessions.py) e
pelo `tools/export_recordings.py`, que vira gravações anotadas em fixtures.
"""
from __future__ import annotations

from segment_scoring import score_words

# Nota esperada por rótulo do gabarito (mesma régua do replay_recording.py)
LABEL_SCORE = {"certo": 100.0, "errado": 0.0, "cantarolei": 0.0}


def result_words(r: dict) -> list[dict]:
    """Palavras que o servidor usaria hoje para o verso gravado.

    Gravação com as duas passadas (formato 2+): aplica o portão de confiança
    atual (com dica se confiável, senão sem dica). Fixtures antigas: só `words`.
    """
    if "prompted_words" in r or "unprompted_words" in r:
        from stt_engine import pick_transcription

        words, _ = pick_transcription(r.get("prompted_words"), r.get("unprompted_words"))
        return words
    return r["words"]


def rescore_session(data: dict) -> tuple[dict[int, float], int]:
    """{verso (a partir de 1): nota} com o score atual, e o total de versos."""
    segments = data["segments"]
    scores = {}
    for r in data["results"]:
        idx = r["segment"]
        words = result_words(r)
        whisper_ran = r.get("used") is not None or bool(r["words"])
        if whisper_ran:
            prev = segments[idx - 1] if idx > 0 else None
            scores[idx + 1] = score_words(segments[idx], prev, words, data["scoring_mode"])["score"]
        else:
            # silêncio/vocalize: não passou pelo Whisper
            scores[idx + 1] = r.get("live_score", r.get("score"))
    return scores, len(segments)


def label_mae(scores: dict[int, float], labels: dict) -> tuple[float | None, int]:
    """Erro médio (0–100) entre a nota e o gabarito, nos versos anotados."""
    errs = []
    for verse, label in (labels or {}).items():
        expected = LABEL_SCORE.get(label)
        got = scores.get(int(verse))
        if expected is None or got is None:
            continue
        errs.append(abs(float(got) - expected))
    return (round(sum(errs) / len(errs), 2) if errs else None), len(errs)
