import unittest

from gerar import TIPOS
from niveis import alinhar_cromaticas, escala_da_armadura, notas_do_acorde

DO = escala_da_armadura(0)
pos = lambda t: t * 2  # 120 bpm: 1 s = 2 tempos  # noqa: E731
ACS_C = [(0, 0, "maj", 0), (2, 0, "maj", 0), (4, 4, "maj", 4), (6, 4, "maj", 4)]  # Dó, Dó, Mi, Mi


class Cromaticas(unittest.TestCase):
    def test_passagem_curta_vai_pro_grau_vizinho(self):
        notas = [(0, .25, 64), (.25, .5, 66), (.5, .75, 67)]  # Mi Fá# Sol sobre Dó: Fá# é passagem
        out, mud = alinhar_cromaticas(notas, [], pos, ACS_C, TIPOS, DO)
        self.assertEqual(out[1][2], 67)  # Sol: nota do acorde
        self.assertEqual(len(mud), 1)

    def test_nota_longa_fica(self):
        notas = [(0, .6, 66)]  # 1,2 tempo
        self.assertEqual(alinhar_cromaticas(notas, [], pos, ACS_C, TIPOS, DO)[0], notas)

    def test_nota_do_acorde_fica_sensivel_do_menor(self):
        # Sol# sobre Mi maior (V de Lá menor): é nota do acorde
        notas = [(2.0, 2.2, 68)]
        self.assertEqual(alinhar_cromaticas(notas, [], pos, ACS_C, TIPOS, DO)[0], notas)

    def test_ataque_de_palavra_fica(self):
        notas = [(0, .25, 66)]
        out, _ = alinhar_cromaticas(notas, [(0.0, .4, "tris")], pos, ACS_C, TIPOS, DO)
        self.assertEqual(out, notas)

    def test_prefere_repetir_a_vizinha(self):
        # Ré Ré# Ré sem acorde: volta pro Ré (bordadura)
        notas = [(10, 10.3, 62), (10.3, 10.45, 63), (10.45, 10.8, 62)]
        out, _ = alinhar_cromaticas(notas, [], pos, [(20, None, None, None)], TIPOS, DO)
        self.assertEqual(out[1][2], 62)

    def test_acorde_no_tempo(self):
        self.assertEqual(notas_do_acorde(ACS_C, TIPOS, 4.5), {4, 8, 11})
        self.assertEqual(notas_do_acorde(ACS_C, TIPOS, 9), set())


if __name__ == "__main__":
    unittest.main()
