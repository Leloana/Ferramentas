"""Melodia no tom: afinação da gravação e notas duvidosas puxadas pra escala."""
import unittest

import numpy as np

from afinacao import afinacao, melodia_no_tom
from gerar import TIPOS


def quadros(trechos, total_s=4.0):
    """trechos: [(ini_s, fim_s, altura contínua)] -> quadros de 10 ms como no cache."""
    n = int(total_s * 100)
    m, per, db = np.zeros(n), np.full(n, .1), np.full(n, -90.)
    for a, b, h in trechos:
        m[int(a * 100):int(b * 100)] = h
        per[int(a * 100):int(b * 100)] = .95
        db[int(a * 100):int(b * 100)] = -5
    return dict(midi=m.tolist(), per=per.tolist(), db=db.tolist())


ACS = [(j, 0, "maj", 0) for j in range(0, 16, 2)]   # Dó maior o tempo todo
POS = lambda t: t * 2                                  # 120 bpm


class Afinacao(unittest.TestCase):
    def test_desvio_da_gravacao(self):
        q = quadros([(0, 3, 60.3), (3, 4, 64.3)])
        self.assertAlmostEqual(afinacao(q), .3, places=2)

    def test_nota_puxando_pra_escala_vai_pro_grau_vizinho(self):
        # Mi cantado baixo (63,4): arredonda pra Mi bemol, mas puxa pro Mi da escala
        q = quadros([(0, .4, 60.0), (.5, .9, 63.4), (1, 1.4, 67.0)] + [(2, 4, 60.0)])
        novas, reg, _ = melodia_no_tom([(0, .4, 60), (.5, .9, 63), (1, 1.4, 67)], q, ACS, TIPOS, POS)
        self.assertEqual([p for *_, p in novas], [60, 64, 67])
        self.assertTrue(any(r["motivo"] == "tom" for r in reg))

    def test_cromatismo_longo_e_centrado_fica(self):
        q = quadros([(0, 1.0, 61.0)] + [(2, 4, 60.0)])
        novas, _, _ = melodia_no_tom([(0, 1.0, 61)], q, ACS, TIPOS, POS)
        self.assertEqual(novas[0][2], 61)

    def test_sem_quadros_nao_mexe(self):
        notas = [(0, .4, 61)]
        self.assertEqual(melodia_no_tom(notas, None, ACS, TIPOS, POS)[0], notas)


if __name__ == "__main__":
    unittest.main()
