"""Regressão do score com partidas reais gravadas (sessão de 2026-09-29).

Cada fixture guarda o que o Whisper ouviu ao vivo (palavras e tempos) em cada
verso, sem o áudio. O teste repontua com o score_engine atual e confere contra
o gabarito abaixo, anotado pelo cantor logo depois de cantar. Mudou o score?
Estes testes dizem se canto certo continua alto e canto errado continua baixo.

Novas partidas: exportar de karaoke/recordings/ (tools/replay_recording.py lê
o mesmo formato) e anotar o gabarito aqui.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from segment_scoring import score_words  # noqa: E402

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "recorded_sessions"

# Versos numerados a partir de 1, como na tela.
GABARITO = {
    # "Essa eu sei": tudo certo, menos "chop chop chop" e "felizes" no lugar de "feliz".
    "ze-assassino-compulsivo-o-terno": {
        "certos_min": {n: 90.0 for n in range(1, 30) if n not in (11, 14, 21, 24)},
        "errou_um_pouco": {11: (60.0, 90.0), 21: (60.0, 90.0), 14: (0.0, 85.0), 24: (0.0, 85.0)},
        "final_min": 92.0,
    },
    # Cantou certo no geral (inglês fraco). 43–46: trecho que não sabia.
    # 12, 28, 52: versos que repetem o anterior e eram zerados pelo "perdão de vazamento".
    "a-wolf-at-the-door-radiohead": {
        "certos_min": {12: 95.0, 28: 95.0, 52: 95.0, 31: 95.0, 50: 95.0, 51: 95.0},
        "errados_max": {43: 20.0, 44: 20.0, 45: 20.0, 46: 20.0},
        "final_min": 78.0,
    },
    # Errou palavras soltas no começo; cantarolou "na na na" de 4:00 a 4:33 (versos 80–85).
    "geni-e-o-zepelim-chico-buarque": {
        "certos_min": {22: 95.0, 46: 95.0, 100: 95.0},
        "errados_max": {n: 15.0 for n in range(80, 86)},
        "media_min": ((20, 70), 85.0),
        "final_min": 80.0,
    },
}


def result_words(r: dict) -> list[dict]:
    """Palavras que o servidor usaria hoje para o verso gravado.

    Gravação com as duas passadas (recorder, formato 2): aplica o portão de confiança
    atual (com dica se confiável, senão sem dica). Fixtures antigas: só `words`.
    """
    if "prompted_words" in r or "unprompted_words" in r:
        from stt_engine import pick_transcription

        words, _ = pick_transcription(r.get("prompted_words"), r.get("unprompted_words"))
        return words
    return r["words"]


def rescore_session(data: dict) -> tuple[dict[int, float], int]:
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


def _rescore(song_id: str) -> tuple[dict[int, float], int]:
    return rescore_session(json.loads((FIXTURES / f"{song_id}.json").read_text(encoding="utf-8")))


class TestRecordedSessions(unittest.TestCase):
    def test_gabarito(self):
        for song_id, gab in GABARITO.items():
            scores, n_segments = _rescore(song_id)
            with self.subTest(song=song_id, check="final"):
                final = sum(scores.values()) / n_segments
                self.assertGreaterEqual(final, gab["final_min"])
            for verse, minimum in gab.get("certos_min", {}).items():
                with self.subTest(song=song_id, verse=verse, check="certo"):
                    self.assertGreaterEqual(scores.get(verse, 0.0), minimum)
            for verse, maximum in gab.get("errados_max", {}).items():
                with self.subTest(song=song_id, verse=verse, check="errado"):
                    self.assertLessEqual(scores.get(verse, 0.0), maximum)
            for verse, (lo, hi) in gab.get("errou_um_pouco", {}).items():
                with self.subTest(song=song_id, verse=verse, check="parcial"):
                    self.assertTrue(lo <= scores.get(verse, 0.0) <= hi, scores.get(verse))
            if "media_min" in gab:
                (first, last), minimum = gab["media_min"]
                with self.subTest(song=song_id, check=f"media {first}-{last}"):
                    chunk = [scores.get(v, 0.0) for v in range(first, last + 1)]
                    self.assertGreaterEqual(sum(chunk) / len(chunk), minimum)


class TestWrongLyrics(unittest.TestCase):
    """120 pares da mesma sessão: áudio de um verso pontuado com a letra de OUTRO verso
    (sem palavras de conteúdo em comum). O Whisper foi rodado com a letra como dica
    ("prompted") e sem ("unprompted"); o servidor usa a segunda quando a primeira não
    merece confiança (stt_engine.prompted_words_trusted)."""

    def _scores(self):
        from stt_engine import prompted_words_trusted

        pairs = json.loads((FIXTURES / "wrong_lyrics_pairs.json").read_text(encoding="utf-8"))
        scores = []
        for p in pairs:
            words = p["prompted"] if prompted_words_trusted(p["prompted"]) else p["unprompted"]
            scores.append(score_words(p["segment"], None, words, "timing")["score"] if words else 0.0)
        return scores

    def test_singing_another_verse_scores_low(self):
        scores = self._scores()
        # Antes: média 16,6 e 3 pares com 100 (o Whisper copiava a dica); meio ponto
        # a partir de 50% de semelhança deixava 11% dos pares acima de 40.
        self.assertLess(sum(scores) / len(scores), 8.0)
        self.assertLess(max(scores), 60.0)
        self.assertLessEqual(sum(s > 40 for s in scores), len(scores) * 0.05)


if __name__ == "__main__":
    unittest.main()
