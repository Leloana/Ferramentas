import unittest

from acompanhamento import acompanhamento_no_teor, densidade_por_compasso, trechos_de_acorde
from gerar import TIPOS
from introducao import TEORES
from test_introducao import ode


class Acompanhamento(unittest.TestCase):
    def test_todos_os_teores_e_niveis(self):
        md, acs = ode()
        fim = max(o + d for o, d, *_ in md) + 4
        for teor in TEORES:
            for nivel in ("facil", "medio", "dificil"):
                ev, pedais, info = acompanhamento_no_teor(acs, md, TIPOS, nivel, teor, fim)
                self.assertTrue(ev, (teor, nivel))
                ordem = sorted((o, o + d) for o, d, _ in ev)
                for (a0, a1), (b0, _) in zip(ordem, ordem[1:]):
                    self.assertLessEqual(a1, b0 + 1e-6, (teor, nivel))     # sem sobreposição
                self.assertLessEqual(max(o + d for o, d, _ in ev), fim + 1e-6)
                self.assertEqual(bool(pedais), teor in ("calma", "lenta", "emotiva"))
                if nivel == "facil":
                    self.assertTrue(all(len({p % 12 for p in ps}) == 1 for _, _, ps in ev))

    def test_canto_denso_simplifica(self):
        md, acs = ode()
        fim = max(o + d for o, d, *_ in md) + 4
        denso = [(i * .25, .25, [72], "la") for i in range(64)]   # 4 notas por tempo, 16 compassos
        _, _, info_denso = acompanhamento_no_teor(acs, denso, TIPOS, "dificil", "emotiva", fim)
        _, _, info_vazio = acompanhamento_no_teor(acs, [], TIPOS, "dificil", "emotiva", fim)
        self.assertGreater(info_denso["compassos_simplificados_pelo_canto"], 0)
        self.assertEqual(info_vazio["compassos_simplificados_pelo_canto"], 0)

    def test_trechos_e_densidade(self):
        acs = [(0, 0, "maj", 0), (2, 0, "maj", 0), (4, None, None, None), (6, 7, "7", 7)]
        self.assertEqual(trechos_de_acorde(acs, 20), [(0, 4, 0, "maj"), (6, 8, 7, "7")])
        self.assertEqual(densidade_por_compasso([(0, 1, [60]), (1, 1, [62]), (4, 1, [64])]), {0: .5, 1: .25})


if __name__ == "__main__":
    unittest.main()
