import unittest

from comparacao_cega import alinhar, trecho_que_mais_mudou
from metricas import _lempel_ziv, dificuldade, grave_embolado, groove


def n(ini, fim, p, mao="esquerda", letra=False):
    return dict(inicio=ini, fim=fim, pitch=p, mao=mao, letra=letra)


class Metricas(unittest.TestCase):
    def test_lempel_ziv_repetitivo_menor(self):
        self.assertLess(_lempel_ziv([1, 2] * 20), _lempel_ziv([1, 5, 2, 7, 3, 3, 9, 1, 4, 8] * 4))

    def test_grave_embolado(self):
        # terça maior em Dó2-Mi2 embola; a mesma terça em Dó4 não
        r = grave_embolado([n(0, 1, 36), n(0, 1, 40), n(1, 2, 60), n(1, 2, 64)])
        self.assertEqual(r["casos"], 1)

    def test_groove(self):
        constante = [n(c * 2.4 + t * .6, c * 2.4 + t * .6 + .5, 48) for c in range(4) for t in range(4)]
        self.assertEqual(groove(constante, 100), 1.0)

    def test_dificuldade(self):
        facil = [n(i, i + 1, 60 + (i % 3), "direita") for i in range(8)]
        dificil = [n(i * .25, i * .25 + .25, 60 + (i * 7) % 24, "direita") for i in range(32)]
        a, b = dificuldade(facil, "direita"), dificuldade(dificil, "direita")
        self.assertLess(a["notas_por_s"], b["notas_por_s"])
        self.assertLess(a["deslocamento_por_s"], b["deslocamento_por_s"])
        self.assertLess(a["extensao"], b["extensao"])


class Alinhamento(unittest.TestCase):
    def test_introducao_desloca_compassos(self):
        mel = [n(i * .6, i * .6 + .5, 60 + i % 5, "direita", True) for i in range(32)]
        com_intro = [dict(x, inicio=x["inicio"] + 9.6, fim=x["fim"] + 9.6) for x in mel]   # 4 compassos a 100 bpm
        k = alinhar(mel, com_intro, 100, 100)
        self.assertEqual(k, 4)
        mudou = [dict(x) for x in com_intro]
        mudou[20]["pitch"] += 2   # compasso 4+5
        c0, valor = trecho_que_mais_mudou(mel, mudou, 100, 100, k)
        self.assertGreater(valor, 0)
        self.assertTrue(c0 <= 9 <= c0 + 3)


class QualidadeMelodia(unittest.TestCase):
    def test_fora_do_tom_repetidas_e_topo(self):
        from metricas import qualidade_melodia
        def m(i, f, p, mao="direita", letra=True):
            return dict(inicio=i, fim=f, pitch=p, mao=mao, letra=letra)
        notas = [m(0, 1, 60), m(1, 2, 62), m(2, 3, 64), m(3, 4, 65), m(4, 5, 67), m(5, 6, 61),   # Dó# fora
                 m(6, 7, 67), m(7, 8, 67), m(0, 1, 72, "esquerda", False)]                        # repetida; esquerda acima
        q = qualidade_melodia(notas)
        self.assertAlmostEqual(q["fora_do_tom"], 12.5)
        self.assertAlmostEqual(q["repetidas"], 12.5)
        self.assertAlmostEqual(q["nao_no_topo"], 12.5)


if __name__ == "__main__":
    unittest.main()
