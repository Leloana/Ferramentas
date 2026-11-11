"""Notas repetidas coladas: sem sílaba viram nota sustentada; com sílaba só com a opção."""
import unittest

from gerar import juntar_repetidas


def n(a, b, p):
    return (a, b, p, a / 2, b / 2)


class Repetidas(unittest.TestCase):
    def test_sem_silaba_junta(self):
        notas = [n(0, .5, 64), n(.5, 1, 64), n(1, 2, 67)]
        saida, letras, j = juntar_repetidas(notas, {0: ["la"], 2: ["le"]})
        self.assertEqual([(a, b, p) for a, b, p, *_ in saida], [(0, 1, 64), (1, 2, 67)])
        self.assertEqual(letras, {0: ["la"], 1: ["le"]})
        self.assertEqual(j, 1)

    def test_com_silaba_fica_por_padrao(self):
        notas = [n(0, .5, 64), n(.5, 1, 64)]
        saida, letras, j = juntar_repetidas(notas, {0: ["co-"], 1: ["-ra"]})
        self.assertEqual((len(saida), j), (2, 0))

    def test_com_silaba_junta_com_a_opcao(self):
        notas = [n(0, .5, 64), n(.5, 1, 64)]
        saida, letras, j = juntar_repetidas(notas, {0: ["co-"], 1: ["-ra-"]}, com_silaba=True)
        self.assertEqual(len(saida), 1)
        self.assertEqual(letras, {0: ["cora-"]})

    def test_nao_colada_ou_outra_altura_fica(self):
        notas = [n(0, .5, 64), n(1, 1.5, 64), n(1.5, 2, 65)]
        self.assertEqual(len(juntar_repetidas(notas, {})[0]), 3)


if __name__ == "__main__":
    unittest.main()
