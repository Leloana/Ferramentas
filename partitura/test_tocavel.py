import unittest

from tocavel import (ajustar, desfazer_sincopes, graves_pra_esquerda, oitava_por_frase, oitavas_da_esquerda,
                     saltos, sincopes, suplementares_sol)


class Sincopes(unittest.TestCase):
    def test_antecipacao_vai_pro_tempo_e_a_anterior_segura(self):
        ev = [(0.0, 1.5, [60]), (1.5, 1.5, [62])]          # Ré antecipado meio tempo
        saida, n = desfazer_sincopes(ev, bpm=100)
        self.assertEqual(n, 1)
        self.assertEqual(saida, [(0.0, 2.0, [60]), (2.0, 1.0, [62])])
        self.assertEqual(sincopes(saida), 0)

    def test_colcheias_no_tempo_ficam(self):
        ev = [(0.0, .5, [60]), (.5, .5, [62]), (1.0, 1.0, [64])]
        self.assertEqual(desfazer_sincopes(ev, bpm=100), (ev, 0))

    def test_nao_atropela_outro_ataque(self):
        ev = [(0.5, 1.0, [60]), (1.0, 1.0, [62])]          # sobreposição: não mexe
        self.assertEqual(desfazer_sincopes(ev)[1], 0)

    def test_nao_deixa_nota_curta_demais(self):
        ev = [(0.5, .75, [60])]                             # ficaria com 1/4 de tempo
        self.assertEqual(desfazer_sincopes(ev)[1], 0)

    def test_salto_grande_fica_antecipado(self):
        # Lá♯ → Lá uma oitava acima a 136 bpm (Fuyu no Hanashi): atrasar deixa 0,44 s pro salto
        ev = [(0.0, 1.5, [70]), (1.5, 1.5, [70]), (3.0, 1.0, [81])]
        self.assertEqual(desfazer_sincopes(ev, bpm=136)[1], 0)
        self.assertEqual(desfazer_sincopes(ev, bpm=60)[1], 1)      # devagar dá tempo


class Oitavas(unittest.TestCase):
    def test_salto_de_duas_oitavas_colado_fica_perto(self):
        me = [(0.0, .5, [36, 43]), (.5, .5, [55, 62]), (1.0, .5, [38, 45])]
        saida, n = oitavas_da_esquerda(me, [], faixa=(28, 64))
        self.assertGreaterEqual(n, 1)
        self.assertLess(saltos(saida), saltos(me))

    def test_nao_encosta_na_direita(self):
        me = [(0.0, 1, [36]), (1.0, 1, [50])]
        md = [(1.0, 1, [52])]
        saida, _ = oitavas_da_esquerda(me, md, faixa=(28, 64))
        self.assertLess(max(saida[1][2]), 52)

    def test_esquerda_parada_nao_muda(self):
        me = [(float(i), 1, [43, 47, 50]) for i in range(8)]
        self.assertEqual(oitavas_da_esquerda(me, [], faixa=(28, 64)), (me, 0))


class Niveis(unittest.TestCase):
    def test_dificil_fica_como_esta(self):
        md = [(0.5, 1.5, [72])]
        me = [(0.0, .5, [36]), (.5, .5, [60]), (1.0, .5, [43])]
        md2, me2, reg = ajustar(md, me, "dificil", 100)
        self.assertEqual((md2, me2, reg), (md, me, {"graves_pra_esquerda": 0}))

    def test_medio_so_mexe_na_esquerda(self):
        md = [(0.5, 1.5, [72])]
        me = [(0.0, .5, [36]), (.5, 1.5, [43])]
        md2, me2, reg = ajustar(md, me, "medio", 100)
        self.assertEqual(md2, md)
        self.assertEqual(reg["sincopes_esquerda"], 1)


class Registro(unittest.TestCase):
    def test_suplementares(self):
        self.assertEqual([suplementares_sol(m) for m in (60, 64, 77, 81, 84, 88)], [1, 0, 0, 1, 2, 3])

    def test_frase_aguda_desce_e_a_grave_fica(self):
        aguda = [(float(i), 1, [p]) for i, p in enumerate([84, 86, 88, 86, 84, 81])]
        grave = [(8.0 + i, 1, [p]) for i, p in enumerate([67, 69, 71, 72, 71, 69])]   # depois de pausa
        novo, n = oitava_por_frase(aguda + grave, [(0.0, 14, [43])])
        self.assertEqual(n, 1)
        self.assertEqual(novo[0][2], [72])
        self.assertEqual(novo[6][2], [67])

    def test_nao_desce_se_encosta_na_esquerda(self):
        md = [(float(i), 1, [p]) for i, p in enumerate([84, 86, 88, 86])]
        me = [(0.0, 4, [60, 76])]
        self.assertEqual(oitava_por_frase(md, me)[1], 0)

    def test_melodia_na_pauta_fica(self):
        md = [(float(i), 1, [p]) for i, p in enumerate([67, 69, 71, 72, 74, 72])]
        self.assertEqual(oitava_por_frase(md, [(0.0, 6, [43])])[1], 0)

    def test_pico_curto_nao_compensa(self):
        md = [(float(i), 1, [p]) for i, p in enumerate([72, 74, 76, 77, 81, 77, 76, 74])]   # 1 Lá5
        self.assertEqual(oitava_por_frase(md, [(0.0, 8, [43])])[1], 0)


class GravesPraEsquerda(unittest.TestCase):
    def test_esquerda_livre_pega_o_grave(self):
        md = [(0.0, 1, [55, 59, 67])]
        md2, me2, n = graves_pra_esquerda(md, [])
        self.assertEqual(n, 2)
        self.assertEqual(md2[0][2], [67])
        self.assertEqual(me2[0][2], [55, 59])

    def test_junta_com_acorde_da_esquerda_se_cabe(self):
        md2, me2, n = graves_pra_esquerda([(0.0, 1, [57, 72])], [(0.0, 1, [48, 52])])
        self.assertEqual((n, me2[0][2]), (1, [48, 52, 57]))

    def test_nao_junta_se_nao_cabe_na_mao(self):
        md = [(0.0, 1, [57, 72])]
        md2, me2, n = graves_pra_esquerda(md, [(0.0, 1, [36, 43])])     # 36..57 = 21 semitons
        self.assertEqual(n, 0)
        self.assertEqual(md2, md)

    def test_esquerda_ocupada_com_outro_ritmo_fica(self):
        md = [(0.0, 1, [57, 72])]
        self.assertEqual(graves_pra_esquerda(md, [(0.5, 1, [48])])[2], 0)

    def test_melodia_nunca_sai(self):
        md = [(0.0, 1, [55])]       # nota sozinha (é a de cima): fica na direita
        self.assertEqual(graves_pra_esquerda(md, [])[2], 0)


if __name__ == "__main__":
    unittest.main()
