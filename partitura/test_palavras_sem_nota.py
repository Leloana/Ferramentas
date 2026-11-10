import unittest

import numpy as np

from palavras_sem_nota import notas_para_palavras, quadros_do_detector


def quadros(dur_s, trechos):
    """trechos: [(ini, fim, midi, per, db)] — quadros de 10 ms; fora deles, silêncio."""
    n = int(dur_s * 100)
    midi, per, db = np.zeros(n), np.zeros(n), np.full(n, -80.0)
    for ini, fim, m, p, d in trechos:
        a, b = int(ini * 100), int(fim * 100)
        midi[a:b], per[a:b], db[a:b] = m, p, d
    return quadros_do_detector(midi, per, db)


class PalavrasSemNota(unittest.TestCase):
    def test_comeco_do_verso_ganha_nota_dos_quadros(self):
        # "Pensem" em 10,0-10,4 s com ataque soprado (confiança .3); a nota só começa em 10,4
        notas = [(10.4, 11.0, 64), (11.0, 11.6, 65)]
        palavras = [(10.0, 10.4, "Pensem"), (10.4, 11.0, "nas"), (11.0, 11.6, "crianças")]
        q = quadros(20, [(10.0, 10.4, 62.2, .3, 0), (10.4, 11.6, 64, .9, 0)])
        saida, log = notas_para_palavras(notas, palavras, q)
        self.assertEqual(saida[0], (10.0, 10.4, 62))
        self.assertEqual(saida[1:], notas)
        self.assertEqual(log[0]["origem"], "quadros")

    def test_erro_de_oitava_do_ataque_volta_pra_regiao(self):
        notas = [(10.4, 11.0, 64)]
        q = quadros(20, [(10.0, 10.4, 50, .3, 0), (10.4, 11.0, 64, .9, 0)])
        saida, _ = notas_para_palavras(notas, [(10.0, 10.4, "Pensem")], q)
        self.assertEqual(saida[0][2], 62)

    def test_salto_de_quinta_nao_e_erro_de_oitava(self):
        notas = [(10.4, 11.0, 64)]
        q = quadros(20, [(10.0, 10.4, 57, .3, 0), (10.4, 11.0, 64, .9, 0)])
        saida, _ = notas_para_palavras(notas, [(10.0, 10.4, "Pensem")], q)
        self.assertEqual(saida[0][2], 57)

    def test_sem_voz_nao_cria(self):
        # alucinação da transcrição na introdução instrumental: voz em silêncio
        notas = [(10.4, 11.0, 64)]
        q = quadros(20, [(10.4, 11.0, 64, .9, 0)])
        saida, log = notas_para_palavras(notas, [(2.0, 2.5, "girl")], q)
        self.assertEqual(saida, notas)
        self.assertEqual(log[0]["motivo"], "sem voz")

    def test_altura_incerta_usa_nota_seguinte(self):
        notas = [(10.4, 11.0, 64)]
        q = quadros(20, [(10.0, 10.4, 0, .05, 0), (10.4, 11.0, 64, .9, 0)])
        saida, log = notas_para_palavras(notas, [(10.0, 10.4, "Pensem")], q)
        self.assertEqual(saida[0], (10.0, 10.4, 64))
        self.assertEqual(log[0]["origem"], "nota seguinte")

    def test_palavra_coberta_nao_muda_nada(self):
        notas = [(10.0, 11.0, 64)]
        saida, log = notas_para_palavras(notas, [(10.1, 10.5, "nas")], None)
        self.assertEqual(saida, notas)
        self.assertEqual(log, [])

    def test_sem_quadros_usa_vizinha_e_nao_sobrepoe(self):
        notas = [(9.0, 10.1, 60), (10.5, 11.0, 64)]
        saida, _ = notas_para_palavras(notas, [(10.1, 10.8, "Pensem")], None)
        criada = [n for n in saida if n not in notas][0]
        self.assertEqual(criada, (10.1, 10.5, 64))
        for a, b in zip(saida, saida[1:]):
            self.assertLessEqual(a[1], b[0] + 1e-9)

    def test_sem_referencia_nao_inventa(self):
        saida, log = notas_para_palavras([(30.0, 31.0, 64)], [(10.0, 10.4, "oi")], None)
        self.assertEqual(saida, [(30.0, 31.0, 64)])
        self.assertFalse(log[0]["criada"])


if __name__ == "__main__":
    unittest.main()
