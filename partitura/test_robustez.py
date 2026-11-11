"""Entradas vazias e degeneradas nos passos do modo leve: nada pode quebrar a geração."""
import unittest

import gerar
import repeticoes
import tocavel


class Vazios(unittest.TestCase):
    def test_ajustar_com_maos_vazias_ou_sem_nota(self):
        for nivel in ("facil", "medio", "dificil"):
            for md, me in (([], []), ([(0.0, 1, [72])], []), ([], [(0.0, 1, [48])]),
                           ([(0.0, 1, []), (1.0, 1, [72])], [(0.0, 2, [])])):
                tocavel.ajustar(md, me, nivel, 120)

    def test_medidas_vazias(self):
        tocavel.medir([], [], 120, "medio")
        self.assertEqual(tocavel.custo_leitura([]), 0.0)
        self.assertEqual(tocavel.oitava_por_frase([], []), ([], 0))

    def test_repeticoes_sem_material(self):
        self.assertEqual(repeticoes.analisar([], []), ([], None, None))
        self.assertEqual(repeticoes.unificar([(0.0, 1, [60])], [], [], None), ([(0.0, 1, [60])], [], 0))

    def test_padronizar_com_audio_que_falha(self):
        md = [(0.0, 1, [72])]
        md2, me2, reg = repeticoes.padronizar(md, [], "/nao/existe.wav", [0.0, .5, 1.0])
        self.assertEqual((md2, reg["grupos"]), (md, 0))

    def test_montar_partitura_degenerada(self):
        gerar.montar_partitura([(0.0, 1, [72], None)], [], [], 100, "t", "s")
        gerar.montar_partitura([(0.0, 1, [60, 62, 64, 65, 67, 69, 71, 72, 74, 76], None)],
                               [(0.0, 1, [24, 36, 48])], [], 100, "t", "s")


if __name__ == "__main__":
    unittest.main()
