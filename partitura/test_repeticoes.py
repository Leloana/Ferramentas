import unittest

import numpy as np

from repeticoes import achados_confirmados, consenso, grupos, impressoes, unificar


def compasso(b, notas):
    """Eventos de um compasso b a partir de [(ataque relativo, duração, [midis])]."""
    return [(4 * b + o, d, ps) for o, d, ps in notas]


TEMA = [(0, 1, [72]), (1, 1, [74]), (2, 1, [76]), (3, 1, [72])]
TEMA_ERRO = [(0, 1, [72]), (1, 1, [75]), (2, 1, [76]), (3, 1, [72])]   # uma nota errada
OUTRO = [(0, 2, [67]), (2, 2, [65])]


class Consenso(unittest.TestCase):
    def test_maioria_vence_o_erro(self):
        c = consenso([TEMA, TEMA_ERRO, TEMA])
        self.assertEqual([ps for _, _, ps in c], [[72], [74], [76], [72]])

    def test_sem_maioria_fica_vazio(self):
        self.assertEqual(consenso([[(0, 1, [60])], [(1, 1, [62])], [(2, 1, [64])]]), [])


class Grupos(unittest.TestCase):
    def test_diagonal_vira_grupos_de_compassos(self):
        self.assertEqual(grupos(12, [(0, 8, 4)]), [[0, 8], [1, 9], [2, 10], [3, 11]])


class Unificar(unittest.TestCase):
    def test_repeticao_escrita_igual(self):
        # 4 compassos de tema, 4 de outra coisa, o tema de novo com uma nota errada e de novo certo
        md = []
        for b in range(4):
            md += compasso(b, TEMA)
        for b in range(4, 8):
            md += compasso(b, OUTRO)
        for b in range(8, 12):
            md += compasso(b, TEMA_ERRO if b == 9 else TEMA)
        for b in range(12, 16):
            md += compasso(b, TEMA)
        me = [(4.0 * b, 4, [48]) for b in range(16)]
        f = impressoes(md, me, 16)
        sim = f @ f.T
        gs = grupos(16, achados_confirmados(sim, [8, 4], limiar=.6, min_compassos=4))
        md2, me2, k = unificar(md, me, gs, sim)
        def notas(b):
            return [ps for o, d, ps in md2 if 4 * b <= o < 4 * b + 4]
        self.assertEqual(notas(9), notas(1))            # o erro sumiu pelo consenso
        self.assertEqual(notas(13), notas(1))
        self.assertEqual(notas(5), [[67], [65]])        # o que não repete fica igual
        self.assertGreater(k, 0)


if __name__ == "__main__":
    unittest.main()
