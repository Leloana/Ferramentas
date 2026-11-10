"""Introdução gerada: forma, harmonia de entrada, nível e reprodutibilidade."""
import unittest

import gerar
from gerar import TIPOS
from introducao import COMPASSOS, TEORES, achar_refrao, gerar_introducao
from maos import tornar_tocavel

# Ode à Alegria (domínio público), Dó maior: A A' B A'
A = [64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64]
A_FIM = [(64, 1.5), (62, .5), (62, 2)]
A2_FIM = [(62, 1.5), (60, .5), (60, 2)]
B = [(62, 1), (62, 1), (64, 1), (60, 1), (62, 1), (64, .5), (65, .5), (64, 1), (60, 1),
     (62, 1), (64, .5), (65, .5), (64, 1), (62, 1), (60, 1), (62, 1), (55, 2)]


def ode():
    md, t = [], 0.0
    letra_a = ["a", "le", "gri", "a", "dos", "can", "tos", "nos", "u", "ne", "a", "to", "dos", "nós"]
    for frase in ([(p, 1) for p in A] + A_FIM, [(p, 1) for p in A] + A2_FIM, B, [(p, 1) for p in A] + A2_FIM):
        sil = letra_a if len(frase) == 15 else ["la"] * len(frase)
        for (p, d), s in zip(frase, sil + ["la"] * len(frase)):
            md.append((t, d, [p], s))
            t += d
        t += 1  # respiro entre frases
    acs = []
    for j in range(0, int(t) + 4, 2):
        acs.append((j, [0, 7, 0, 7, 9, 5, 7, 0][(j // 2) % 8], ["maj", "7", "maj", "7", "m", "maj", "7", "maj"][(j // 2) % 8], 0))
    return md, acs


class Introducao(unittest.TestCase):
    def test_refrao_pela_letra(self):
        md, _ = ode()
        frase, como = achar_refrao(md)
        self.assertIn("letra", como)
        self.assertEqual(frase[0][3], "a")

    def test_forma_em_todos_os_teores_e_niveis(self):
        md, acs = ode()
        for teor in TEORES:
            for nivel in ("facil", "medio", "dificil"):
                d, e, cf, info = gerar_introducao(md, acs, TIPOS, nivel, teor, inicio_musica=0, semente="ode")
                L = 4 * COMPASSOS[nivel]
                for o, du, ps, *_ in d + e:
                    self.assertGreaterEqual(o, 0)
                    self.assertLessEqual(o + du, L + 1e-6, (teor, nivel))
                for mao in (d, e):  # sem sobreposição dentro da mão
                    ev = sorted((o, o + du) for o, du, *_ in mao)
                    for (a0, a1), (b0, _) in zip(ev, ev[1:]):
                        self.assertLessEqual(a1, b0 + 1e-6, (teor, nivel))
                # cadência: dominante do primeiro acorde da música (Dó -> Sol7)
                self.assertEqual(cf[-1][1:], (7, "7"), (teor, nivel))
                if nivel == "facil":
                    self.assertTrue(all(len(ps) == 1 for _, _, ps, *_ in d))
                    # esquerda: uma nota, ou oitava (mesma nota) na épica
                    self.assertTrue(all(len({p % 12 for p in ps}) == 1 for _, _, ps, *_ in e))
                    self.assertTrue(all(du >= 1 - 1e-6 for _, du, *_ in d + e))
                if teor in ("calma", "lenta"):  # esquerda só com notas longas
                    self.assertTrue(all(du >= 2 - 1e-6 for _, du, *_ in e), (teor, nivel))

    def test_epica_tem_tensao_e_crescendo(self):
        md, acs = ode()
        for nivel in ("facil", "medio", "dificil"):
            d, e, cf, info = gerar_introducao(md, acs, TIPOS, nivel, "epica", 0, "ode")
            graus = [(r - 0) % 12 for _, r, _ in cf]
            self.assertIn(8, graus)    # bVI (Láb)
            self.assertIn(10, graus)   # bVII (Sib)
            self.assertEqual([v for _, v in info["dinamicas"]], ["mp", "f", "ff"])
            self.assertTrue(any(len(ps) >= 2 for _, _, ps, *_ in e))   # oitavas/acordes na esquerda
            # sus4: Dó (4ª de Sol) antes do Si (3ª) no último compasso
            ultimas = [ps[-1] % 12 for o, _, ps, *_ in d if o >= 4 * info["compassos"] - 4]
            self.assertEqual(ultimas[:2], [0, 11])

    def test_teores_diferentes_soam_diferente(self):
        md, acs = ode()
        saidas = {t: gerar_introducao(md, acs, TIPOS, "medio", t, 0, "ode")[:2] for t in TEORES}
        self.assertEqual(len({repr(v) for v in saidas.values()}), len(TEORES))

    def test_reprodutivel_e_variacao(self):
        md, acs = ode()
        a = gerar_introducao(md, acs, TIPOS, "dificil", "epica", 0, "ode")
        self.assertEqual(a, gerar_introducao(md, acs, TIPOS, "dificil", "epica", 0, "ode"))
        outras = {repr(gerar_introducao(md, acs, TIPOS, "dificil", "epica", 0, "ode", variacao=v)[0]) for v in range(1, 6)}
        self.assertGreater(len(outras | {repr(a[0])}), 1)

    def test_partitura_com_introducao_e_tocavel(self):
        md, acs = ode()
        fim = max(o + d for o, d, *_ in md) + 4
        from niveis import suavizar_baixo
        me = suavizar_baixo(gerar_fechar(acs, fim), "medio")
        intro = gerar_introducao(md, acs, TIPOS, "medio", "emotiva", 0, "ode")
        md2, me2, cf, marcas = gerar.com_introducao(md, me, [(0, 0, "maj")], intro)
        self.assertEqual(min(o for o, *_ in md2), -16)
        prot = {(round(o, 6), p) for o, _, ps, *_ in md for p in ps}
        md3, me3, dmd, dme, rel = tornar_tocavel(md2, me2, "medio", 100, prot)
        self.assertEqual(rel["resumo"]["restantes_na_melodia"], 0)
        sc, _ = gerar.montar_partitura(md3, me3, cf, 100, "Ode", "teste", dedos_md=dmd, dedos_me=dme, marcas=marcas)
        from music21 import expressions
        textos = [t.content for t in sc.recurse().getElementsByClass(expressions.TextExpression)]
        self.assertIn("Introdução gerada (emotiva)", textos)
        self.assertIn("Música", textos)


def gerar_fechar(acs, fim):
    from niveis import fechar_acordes, mao_esquerda_acordes
    return fechar_acordes(mao_esquerda_acordes(acs, "medio", fim, TIPOS))


if __name__ == "__main__":
    unittest.main()
