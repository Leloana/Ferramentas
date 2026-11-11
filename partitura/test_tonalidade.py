"""Nota fora do tom no arranjo da IA, por regras de harmonia."""
import unittest

from gerar import TIPOS
from tonalidade import corrigir_tom, tons_por_trecho

ACS = [(j, 0, "maj7", 0) for j in range(0, 32, 2)]          # Cmaj7 o tempo todo


def escala_do(o):
    return [(o + k, 1, [p]) for k, p in enumerate([60, 62, 64, 65, 67, 69, 71, 72])]


class Tonalidade(unittest.TestCase):
    def test_tom_de_do_maior(self):
        tons, _ = tons_por_trecho(escala_do(0) + escala_do(8) + [(16, 4, [48, 52, 55])])
        self.assertEqual(set(tons.values()), {(0, "maior")})

    def test_nota_firme_fora_do_tom_e_sem_funcao_muda(self):
        md = escala_do(0) + [(8, 2, [68]), (10, 2, [72]), (12, 2, [60])]   # Láb firme, chega e sai por salto
        me = [(o, 2, [48]) for o in range(0, 14, 2)]
        md2, _, reg = corrigir_tom(md, me, ACS, TIPOS)
        self.assertIn(dict(mao="direita", ini=8, antes=68, depois=67, motivo="fora do tom"), reg)

    def test_bordadura_cromatica_e_setima_maior_ficam(self):
        md = escala_do(0) + [(8, .5, [67]), (8.5, .5, [68]), (9, 1, [67]), (10, 2, [71])]  # Sol-Láb-Sol; Si sobre Dó
        me = [(o, 2, [48]) for o in range(0, 12, 2)]
        md2, _, reg = corrigir_tom(md, me, ACS, TIPOS)
        self.assertEqual(reg, [])


if __name__ == "__main__":
    unittest.main()
