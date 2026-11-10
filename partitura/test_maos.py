import unittest

from maos import Mao, Nota, dedilhar, separar_maos, tornar_tocavel


def seq(ps, dur=.5, inicio=0.0, protegida=False):
    return [Nota(i, inicio + i * dur, inicio + (i + 1) * dur, p, i, protegida) for i, p in enumerate(ps)]


class Dedilhado(unittest.TestCase):
    def test_escala_maior_direita(self):
        ns = seq([60, 62, 64, 65, 67, 69, 71, 72])
        dedos, probs, _, _ = dedilhar(Mao("direita", "medio", 100), ns)
        self.assertEqual([dedos[n.id] for n in ns], [1, 2, 3, 1, 2, 3, 4, 5])
        self.assertEqual(probs, [])

    def test_escala_descendo_esquerda(self):
        ns = seq([48, 47, 45, 43, 41, 40, 38, 36])
        dedos, probs, _, _ = dedilhar(Mao("esquerda", "medio", 100), ns)
        self.assertEqual([dedos[n.id] for n in ns], [1, 2, 3, 1, 2, 3, 4, 5])
        self.assertEqual(probs, [])

    def test_acorde_fechado_esquerda(self):
        ns = [Nota(i, 0, 1, p, 0, False) for i, p in enumerate([36, 40, 43])]
        dedos, probs, _, _ = dedilhar(Mao("esquerda", "medio", 100), ns)
        self.assertEqual([dedos[n.id] for n in ns], [5, 3, 1])
        self.assertEqual(probs, [])

    def test_acorde_aberto_demais(self):
        ns = [Nota(i, 0, 1, p, 0, False) for i, p in enumerate([36, 52, 58])]
        _, probs, _, _ = dedilhar(Mao("esquerda", "medio", 100), ns)
        self.assertEqual(probs[0]["tipo"], "abertura")

    def test_nota_segurada_prende_a_mao(self):
        # Dó4 segurado dois tempos; Ré5 (14 semitons acima) entra no meio: a mão não alcança
        ns = [Nota(0, 0, 2, 60, 0, False), Nota(1, 1, 2, 74, 1, False)]
        _, probs, _, _ = dedilhar(Mao("direita", "medio", 100), ns)
        self.assertIn("ligada", {p["tipo"] for p in probs})
        # a mesma nota entrando depois que o Dó4 acabou é só um salto com tempo de sobra
        ns = [Nota(0, 0, 1, 60, 0, False), Nota(1, 2, 3, 74, 1, False)]
        _, probs, _, _ = dedilhar(Mao("direita", "medio", 100), ns)
        self.assertEqual(probs, [])

    def test_segurada_que_cabe(self):
        # Dó4 segurado com o 1, Mi e Sol por cima: cabe
        ns = [Nota(0, 0, 2, 60, 0, False), Nota(1, 1, 1.5, 64, 1, False), Nota(2, 1.5, 2, 67, 2, False)]
        dedos, probs, _, _ = dedilhar(Mao("direita", "medio", 100), ns)
        self.assertEqual(probs, [])
        self.assertEqual(dedos[0], 1)

    def test_mais_notas_que_dedos(self):
        ns = [Nota(0, 0, 2, 60, 0, False)] + [Nota(i, 1, 2, p, i, False) for i, p in
                                               enumerate([62, 64, 65, 67, 69], start=1)]
        _, probs, _, _ = dedilhar(Mao("direita", "dificil", 100), ns)
        self.assertIn("dedos", {p["tipo"] for p in probs})

    def test_salto_depende_do_nivel(self):
        # oitava cabe na mão sem mudar de lugar (5 no grave, 1 no agudo)
        self.assertEqual(dedilhar(Mao("esquerda", "facil", 100), seq([36, 48], dur=.5))[1], [])
        # décima segunda em semínima a 100 bpm: dá no difícil, não dá no fácil; no fácil com 4 tempos dá
        _, probs_d, _, _ = dedilhar(Mao("esquerda", "dificil", 100), seq([36, 55], dur=1))
        _, probs_f, _, _ = dedilhar(Mao("esquerda", "facil", 100), seq([36, 55], dur=1))
        self.assertEqual(probs_d, [])
        self.assertEqual(probs_f[0]["tipo"], "salto")
        self.assertEqual(dedilhar(Mao("esquerda", "facil", 100), seq([36, 55], dur=4))[1], [])


# digitações de método (escalas, arpejos, cinco dedos, melodias infantis)
REFERENCIAS = [
    ("direita", [60, 62, 64, 65, 67, 69, 71, 72], [1, 2, 3, 1, 2, 3, 4, 5]),
    ("direita", [72, 71, 69, 67, 65, 64, 62, 60], [5, 4, 3, 2, 1, 3, 2, 1]),
    ("esquerda", [48, 47, 45, 43, 41, 40, 38, 36], [1, 2, 3, 1, 2, 3, 4, 5]),
    ("esquerda", [36, 38, 40, 41, 43, 45, 47, 48], [5, 4, 3, 2, 1, 3, 2, 1]),
    ("direita", [60, 62, 64, 65, 67, 65, 64, 62, 60], [1, 2, 3, 4, 5, 4, 3, 2, 1]),
    ("direita", [60, 64, 67, 72, 67, 64, 60], [1, 2, 3, 5, 3, 2, 1]),
    ("esquerda", [36, 40, 43, 48, 43, 40, 36], [5, 3, 2, 1, 2, 3, 5]),
    ("direita", [67, 67, 69, 67, 72, 71], [1, 1, 2, 1, 4, 3]),
    ("direita", [64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 64, 62, 62],
     [3, 3, 4, 5, 5, 4, 3, 2, 1, 1, 2, 3, 3, 2, 2]),
    ("direita", [67, 64, 64, 65, 62, 62, 60, 62, 64, 65, 67, 67, 67], [5, 3, 3, 4, 2, 2, 1, 2, 3, 4, 5, 5, 5]),
    ("direita", [62, 64, 66, 67, 69, 71, 73, 74], [1, 2, 3, 1, 2, 3, 4, 5]),
]


class Referencias(unittest.TestCase):
    def test_concorda_com_metodo(self):
        acertos = total = 0
        for lado, ps, livro in REFERENCIAS:
            ns = seq(ps)
            dedos = dedilhar(Mao(lado, "medio", 100), ns)[0]
            acertos += sum(dedos[n.id] == f for n, f in zip(ns, livro))
            total += len(livro)
        self.assertGreaterEqual(acertos / total, .95, f"{acertos}/{total}")


class Correcao(unittest.TestCase):
    def test_melodia_protegida_nunca_muda(self):
        md = [(i * .25, .25, [p], "la") for i, p in enumerate([60, 84, 60, 84])]
        prot = {(round(o, 6), p) for o, _, ps, *_ in md for p in ps}
        md2, _, _, _, rel = tornar_tocavel(md, [], "facil", 120, prot)
        self.assertEqual(md2, md)
        self.assertGreater(rel["resumo"]["restantes_na_melodia"], 0)

    def test_fecha_acorde_sem_perder_classes(self):
        me = [(0, 2, [36, 52, 58]), (2, 2, [43, 50, 55, 59])]
        _, me2, _, _, rel = tornar_tocavel([], me, "medio", 100)
        for a, b in zip(me, me2):
            self.assertEqual({p % 12 for p in a[2]}, {p % 12 for p in b[2]})
            self.assertEqual(min(a[2]), min(b[2]))
            self.assertLessEqual(max(b[2]) - min(b[2]), 12)
        self.assertEqual(rel["resumo"]["restantes"], 0)

    def test_salto_rapido_muda_oitava_do_acompanhamento(self):
        me = [(0, .25, [38]), (.25, .25, [62]), (.5, .5, [41])]
        _, me2, _, _, rel = tornar_tocavel([], me, "medio", 100)
        self.assertEqual(me2[1][2], [50])
        self.assertEqual(rel["resumo"]["restantes"], 0)

    def test_maos_nao_se_cruzam(self):
        md = [(0, 2, [55], "a")]
        me = [(0, 2, [43, 54, 59])]
        prot = {(0.0, 55)}
        me2, corr = separar_maos(md, me, "medio", prot)
        self.assertLess(max(me2[0][2]), 55)
        self.assertEqual(min(me2[0][2]), 43)
        self.assertTrue(corr)

    def test_dedos_por_evento(self):
        md = [(i * .5, .5, [p], None) for i, p in enumerate([60, 62, 64, 65, 67])]
        _, _, d_md, _, _ = tornar_tocavel(md, [], "facil", 100, mostrar="todos")
        self.assertEqual(d_md, [[1], [2], [3], [4], [5]])  # cinco dedos, sem mudar a mão
        _, _, d_md, _, _ = tornar_tocavel(md, [], "medio", 100)
        self.assertEqual(d_md[0], [1])          # primeira nota sempre
        self.assertTrue(any(d is None for d in d_md))  # no médio só nas mudanças


if __name__ == "__main__":
    unittest.main()


class OitavaEDedos(unittest.TestCase):
    def test_8va_escrita_abaixo_e_midi_na_altura_certa(self):
        import re
        import tempfile
        from pathlib import Path
        import pretty_midi
        import gerar
        alturas = [72, 74, 76, 84, 86, 88, 89, 91, 88, 84, 76, 74]
        md = [(i * .5, .5, [p], None) for i, p in enumerate(alturas)]
        sc, _ = gerar.montar_partitura(md, [(0, 4, [48]), (4, 2, [43])], [], 100, "t", "s")
        with tempfile.TemporaryDirectory() as tmp:
            xml, mid = Path(tmp) / "x.musicxml", Path(tmp) / "x.mid"
            sc.write("musicxml", fp=str(xml))
            texto = xml.read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r'<octave-shift[^>]*type="down"', texto)), 1)
            gerar.salvar_midi_notas(sc, mid, xml)
            tocadas = [n.pitch for i in pretty_midi.PrettyMIDI(str(mid)).instruments for n in i.notes if n.pitch >= 60]
            self.assertEqual(tocadas, alturas)

    def test_dedos_ao_lado_da_nota(self):
        import gerar
        svg = ('<g id="n1" class="note"><g class="notehead"><use xlink:href="#x" transform="translate(2000, 1500) scale(1)"/></g></g>'
               '<g id="f1" class="fing" data-startid="#n1"><text x="2100" y="900" text-anchor="middle" font-size="0px">'
               '<tspan class="text"><tspan font-size="200px">3</tspan></tspan></text></g>')
        saida = gerar.dedos_ao_lado(svg)
        self.assertIn('x="1950" y="1572" text-anchor="end"', saida)
        # colado na fórmula de compasso: fica onde estava
        com_compasso = '<g id="m" class="meterSig"><use transform="translate(1700, 1500) scale(1)"/></g>' + svg
        # colado na fórmula de compasso: vai pra direita da cabeça
        self.assertIn('text-anchor="start"', gerar.dedos_ao_lado(com_compasso))
        # e se a direita também estiver ocupada (outra nota logo depois), fica em cima
        vizinha = ('<g id="n2" class="note"><g class="notehead"><use xlink:href="#x" '
                   'transform="translate(2300, 1500) scale(1)"/></g></g>')
        self.assertIn('x="2100" y="900" text-anchor="middle"', gerar.dedos_ao_lado(com_compasso + vizinha))
