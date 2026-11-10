"""Alinhamento da letra pelo karaokê, sem modelo: áudio de zeros e alinhador falso."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import alinhamento

TEMPOS = {  # "gravação" de 60 s; o 3º verso o alinhador não acha
    "ouvi": (10.2, 10.6), "dizer": (10.7, 11.3),
    "do": (13.1, 13.3), "teu": (13.4, 13.7), "olhar": (13.8, 14.6),
}
LETRA = "Ouvi dizer\nDo teu olhar\nNão sei por que"
LRC = "[00:10.00]Ouvi dizer\n[00:13.00]Do teu olhar\n[00:40.00]Não sei por que"


def alinhador_falso(t0, t1, palavras):
    if "nao" in palavras:
        raise RuntimeError("CTC: frames insuficientes")
    return [(TEMPOS[w][0], TEMPOS[w][1], .9) if w in TEMPOS and t0 <= TEMPOS[w][0] and TEMPOS[w][1] <= t1
            else None for w in palavras]


@unittest.skipIf(alinhamento._importar_karaoke() is None, "karaokê ou dependências ausentes")
class Alinhamento(unittest.TestCase):
    def rodar(self, whisper):
        audio = np.zeros(60 * 16000, dtype=np.float32)
        with patch("utils.audio.load_audio_full", return_value=audio):
            return alinhamento.palavras_alinhadas(Path("voz.wav"), LETRA, "pt", whisper=whisper,
                                                  sincronizada=LRC, align_fn=alinhador_falso)

    def test_letra_oficial_no_tempo_e_whisper_so_no_buraco(self):
        whisper = [(0.5, 1.2, "The"), (1.3, 2.0, "girl"),          # alucinação na introdução
                   (10.2, 10.6, "ouvir"), (10.7, 11.3, "dize"),     # Whisper errando a grafia
                   (40.2, 40.5, "Não"), (40.6, 40.9, "sei")]        # verso que o alinhador perdeu
        palavras, rel = self.rodar(whisper)
        textos = [t for _, _, t in palavras]
        self.assertEqual(textos[:5], ["Ouvi", "dizer", "Do", "teu", "olhar"])
        self.assertAlmostEqual(palavras[0][0], 10.2, places=2)
        self.assertNotIn("girl", textos)          # fora de verso: não entra
        self.assertNotIn("ouvir", textos)         # verso alinhado: vale a letra oficial
        self.assertIn("sei", textos)              # verso perdido: entra o Whisper
        self.assertEqual(rel["alinhados"], 2)
        self.assertEqual(rel["palavras_whisper_nos_buracos"], 2)
        inicios = [a for a, _, _ in palavras]
        self.assertEqual(inicios, sorted(inicios))

    def test_poucos_versos_alinhados_volta_pro_whisper(self):
        audio = np.zeros(60 * 16000, dtype=np.float32)
        with patch("utils.audio.load_audio_full", return_value=audio):
            palavras, rel = alinhamento.palavras_alinhadas(
                Path("voz.wav"), LETRA, "pt", sincronizada=LRC,
                align_fn=lambda t0, t1, ws: (_ for _ in ()).throw(RuntimeError("falhou")))
        self.assertIsNone(palavras)
        self.assertEqual(rel["alinhados"], 0)


class Segmentos(unittest.TestCase):
    def test_segments_do_karaoke(self):
        segs = [
            {"sing_start": 10.0, "sing_end": 12.0, "align": "window",
             "lyrics_timed": [{"word": "Ouvi", "expected_start": .2, "expected_end": .6},
                              {"word": "dizer", "expected_start": .7, "expected_end": 1.3}]},
            {"sing_start": 40.0, "sing_end": 42.0, "align": "fallback",
             "lyrics_timed": [{"word": "Não", "expected_start": 0.05, "expected_end": .3}]},
        ]
        palavras, ruins = alinhamento.palavras_de_segmentos(segs)
        self.assertEqual(palavras, [(10.2, 10.6, "Ouvi"), (10.7, 11.3, "dizer")])
        self.assertEqual(ruins, [(40.0, 42.0)])

    def test_musica_do_karaoke(self):
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            pasta, trabalho = Path(tmp) / "a-flor-los-hermanos", Path(tmp) / "trabalho"
            pasta.mkdir()
            sr = 22050
            t = np.arange(sr * 2) / sr
            sf.write(str(pasta / "vocal.mp3"), .3 * np.sin(2 * np.pi * 220 * t), sr, format="MP3")
            sf.write(str(pasta / "backing_track.mp3"), .3 * np.sin(2 * np.pi * 110 * t), sr, format="MP3")
            (pasta / "meta.json").write_text(json.dumps({
                "meta": {"title": "A Flor", "artist": "Los Hermanos", "language": "pt"},
                "lyrics": {"plain_lyrics": "Ouvi dizer"},
                "alignment_quality": {"score": 95}, "needs_review": False}), encoding="utf-8")
            (pasta / "segments.json").write_text(json.dumps([
                {"sing_start": .5, "sing_end": 1.5, "align": "window",
                 "lyrics_timed": [{"word": "Ouvi", "expected_start": 0, "expected_end": .4}]}]), encoding="utf-8")
            (pasta / "lyrics.lrc").write_text("[00:00.50]Ouvi dizer", encoding="utf-8")
            k = alinhamento.musica_do_karaoke(pasta, trabalho)
            self.assertEqual((k["titulo"], k["artista"], k["idioma"]), ("A Flor", "Los Hermanos", "pt"))
            self.assertEqual(k["palavras"], [(0.5, 0.9, "Ouvi")])
            self.assertTrue(k["audio"].exists() and k["voz"].exists())
            self.assertIn("a-flor-los-hermanos", k["acompanhamento"].name)
            self.assertEqual(k["synced_lyrics"], "[00:00.50]Ouvi dizer")
            # letra marcada pra revisão com nota baixa: a partitura não usa
            meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
            meta.update(needs_review=True, alignment_quality={"score": 40})
            (pasta / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            self.assertIsNone(alinhamento.musica_do_karaoke(pasta, trabalho)["palavras"])


if __name__ == "__main__":
    unittest.main()
