"""Limpeza pra melodia ficar reconhecível."""
import unittest

from limpeza import juntar_repetidas_esquerda, melodia_no_topo, tirar_bordaduras


class Limpeza(unittest.TestCase):
    def test_bordadura_falsa_vira_a_nota_vizinha(self):
        notas = [(0, 1, 69, 0, .5), (1, 1.5, 71, .5, .75), (1.5, 2, 69, .75, 1)]
        saida, n = tirar_bordaduras(notas, {0: ["a"]})
        self.assertEqual([x[2] for x in saida], [69, 69, 69])
        self.assertEqual(n, 1)
        # com sílaba própria fica
        self.assertEqual(tirar_bordaduras(notas, {0: ["a"], 1: ["e"]})[1], 0)

    def test_repetidas_da_esquerda_seguram_no_meio_compasso(self):
        me = [(0, .5, [46]), (.5, .5, [46]), (1, .5, [46]), (1.5, .5, [46]), (2, .5, [46])]
        self.assertEqual(juntar_repetidas_esquerda(me), [(0, 2.0, [46]), (2, .5, [46])])

    def test_acompanhamento_acima_da_melodia_sai(self):
        md = [(0, 2, [67], "la")]
        me = [(0, 2, [48, 55, 66, 69])]       # 66 colada (1 semitom abaixo) e 69 acima saem
        _, me2, n = melodia_no_topo(md, me)
        self.assertEqual(me2, [(0, 2, [48, 55])])
        self.assertEqual(n, 2)

    def test_sem_canto_nao_mexe(self):
        md = [(0, 2, [72])]
        me = [(0, 2, [74])]
        self.assertEqual(melodia_no_topo(md, me)[1], me)


if __name__ == "__main__":
    unittest.main()
