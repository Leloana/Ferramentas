"""Tempo 1 corrigido pela harmonia (o baixo bate forte no 1 e no 3)."""
import unittest

from gerar import corrigir_fase


class Fase(unittest.TestCase):
    def test_trocas_no_tempo_3_andam_duas_batidas(self):
        # acorde muda sempre na posição 2, 6, 10... (tempo 3): a fase estava meio compasso errada
        acs = []
        for k in range(20):
            raiz = 0 if (k + 1) // 2 % 2 == 0 else 7
            acs.append((2 * k, raiz, "maj", raiz))
        fase, novos, mudou = corrigir_fase(1, acs)
        self.assertTrue(mudou)
        self.assertEqual(fase, 3)
        trocas = [j for (j, r, *_), (_, r0, *_) in zip(novos[1:], novos) if r != r0]
        self.assertTrue(all(int(j) % 4 == 0 for j in trocas))

    def test_trocas_no_tempo_1_ficam(self):
        acs = [(2 * k, 0 if k // 2 % 2 == 0 else 7, "maj", 0) for k in range(20)]
        self.assertFalse(corrigir_fase(0, acs)[2])


if __name__ == "__main__":
    unittest.main()
