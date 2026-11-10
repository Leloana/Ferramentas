import tempfile
import unittest
from pathlib import Path

from experimento_6faixas import (comparar_sequencias, contra_referencia, ler_acorde, ler_referencia,
                                 trocas_por_minuto)


class Experimento(unittest.TestCase):
    def test_ler_acorde(self):
        self.assertEqual(ler_acorde("Am7"), (9, "m7"))
        self.assertEqual(ler_acorde("Bb7M"), (10, "maj7"))
        self.assertEqual(ler_acorde("F#m7(b5)"), (6, "m7b5"))
        self.assertEqual(ler_acorde("C"), (0, "maj"))
        self.assertEqual(ler_acorde("Ebm6"), (3, "m6"))
        self.assertEqual(ler_acorde("G7"), (7, "7"))
        self.assertIsNone(ler_acorde("N.C."))

    def test_comparar(self):
        a = [(0, 0, "maj"), (2, 7, "7"), (4, 9, "m"), (6, None, None)]
        b = [(0, 0, "maj"), (2, 7, "maj"), (4, 2, "m"), (6, 0, "maj")]
        c = comparar_sequencias(a, b)
        self.assertEqual(c["janelas"], 3)
        self.assertAlmostEqual(c["mesma_fundamental"], .667, places=3)
        self.assertAlmostEqual(c["mesmo_acorde"], .333, places=3)
        self.assertAlmostEqual(c["mesma_familia"], .667, places=3)

    def test_trocas_e_referencia(self):
        acs = [(0, 0, "maj"), (2, 0, "maj"), (4, 7, "7"), (6, 0, "maj")]
        self.assertEqual(trocas_por_minuto(acs, .5), 2 / (8 * .5 / 60))
        ref = [(0.0, 2.0, (0, "maj")), (2.0, 3.0, (7, "7"))]
        r = contra_referencia(acs, ref, lambda p: p * .5)
        self.assertEqual(r["janelas"], 3)
        self.assertAlmostEqual(r["fundamental"], 1.0)
        with tempfile.TemporaryDirectory() as t:
            arq = Path(t) / "m.csv"
            arq.write_text("# inicio,fim,acorde\n0,2,C\n2,3,G7\n", encoding="utf-8")
            self.assertEqual(ler_referencia(arq), ref)


if __name__ == "__main__":
    unittest.main()
