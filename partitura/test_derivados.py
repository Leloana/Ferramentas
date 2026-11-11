"""Fácil e difícil derivados do médio."""
import unittest

from derivados import dificil_de_medio, facil_de_medio
from gerar import TIPOS

ACS = [(j, 0, "maj7", 0) for j in range(0, 16, 2)]   # Cmaj7: a 7ª (Si) não pode entrar no que é acrescentado


class Derivados(unittest.TestCase):
    def test_facil_guarda_ritmo_da_melodia_e_tira_instrumental_rapido(self):
        md = [(0, .5, [72, 76], "la"), (.5, .5, [74], "le"), (1, .25, [79]), (1.25, .75, [77], "li")]
        me = [(0, 2, [48, 52, 55]), (2, 2, [43, 47, 50])]
        d, e, _ = facil_de_medio(md, me, ACS, TIPOS)
        self.assertEqual([(o, du, ps) for o, du, ps, *_ in d], [(0, .5, [76]), (.5, .5, [74]), (1.25, .75, [77])])
        self.assertTrue(all(len(ps) == 1 for _, _, ps in e))

    def test_dificil_arpeja_so_com_a_triade(self):
        md = [(0, 2, [76], "la")]
        me = [(0, 2, [48])]                      # nota solta longa vira arpejo do acorde
        d, e, marcas = dificil_de_medio(md, me, ACS, TIPOS, bpm=100)
        alturas = {p for _, _, ps in e for p in ps}
        self.assertGreater(len(e), 1)
        self.assertTrue(all(p % 12 in {0, 4, 7} for p in alturas))
        self.assertTrue(any(t == "pedal" for _, t, _ in marcas))
        self.assertTrue(any(t == "fermata" for _, t, _ in marcas))
        self.assertGreater(len(d[0][2]), 1)       # nota longa ganhou nota do acorde embaixo
        self.assertTrue(all(p % 12 in {0, 4, 7} for p in d[0][2]))


if __name__ == "__main__":
    unittest.main()
