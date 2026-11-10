"""Cifras na pauta de cima mesmo onde a direita só tem pausa."""
import unittest

import gerar


class CifraEmPausa(unittest.TestCase):
    def montar(self):
        from music21 import harmony, note, stream
        md = [(0, 4, [64], "la")]                       # direita só no 1º compasso
        me = [(0, 4, [48]), (4, 2, [48]), (6, 2, [43])]  # esquerda vai até o 2º
        cf = [(0, 0, "maj"), (4, 0, "maj"), (6, 7, "7")]
        sc, _ = gerar.montar_partitura(md, me, cf, 100, "t", "s")
        return sc, harmony, note, stream

    def test_direita_tem_o_ultimo_compasso_e_todas_as_cifras(self):
        sc, harmony, note, stream = self.montar()
        cima, baixo = sc.parts[0], sc.parts[1]
        self.assertEqual(len(cima.getElementsByClass(stream.Measure)), len(baixo.getElementsByClass(stream.Measure)))
        self.assertEqual(len(list(cima.recurse().getElementsByClass(harmony.ChordSymbol))), 3)

    def test_pausa_partida_no_tempo_da_cifra(self):
        sc, harmony, note, stream = self.montar()
        m2 = sc.parts[0].getElementsByClass(stream.Measure)[1]
        ataques = sorted(float(r.getOffsetBySite(r.activeSite)) for r in m2.recurse().getElementsByClass(note.Rest))
        self.assertIn(2.0, ataques)
        self.assertEqual(len(m2.getElementsByClass(stream.Voice)), 0)


if __name__ == "__main__":
    unittest.main()
