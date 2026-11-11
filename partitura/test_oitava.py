"""8va pela soma de linhas suplementares (em cima e embaixo pesam igual), sem abrir e fechar à toa."""
import unittest

import gerar


def linhas_8va(alturas, dur=.5):
    from music21 import spanner
    md = [(i * dur, dur, [p], None) for i, p in enumerate(alturas)]
    sc, _ = gerar.montar_partitura(md, [(0, 4 * (len(alturas) // 8 + 1), [48])], [], 100, "t", "s")
    d = sc.parts[0]
    linhas = list(d.recurse().getElementsByClass(spanner.Ottava))
    faixas = [(float(l.getFirst().getOffsetInHierarchy(d)), float(l.getLast().getOffsetInHierarchy(d))) for l in linhas]
    escritas = []   # altura desenhada: a que soa, uma oitava abaixo dentro da 8va (como o Verovio desenha)
    for n in d.recurse().notes:
        o = float(n.getOffsetInHierarchy(d))
        em8 = any(a <= o <= b for a, b in faixas)
        escritas += [p.diatonicNoteNum - 7 * em8 for p in n.pitches]
    return linhas, sum(gerar._suplementares(x) for x in escritas)


class Oitava(unittest.TestCase):
    def test_trecho_agudo_que_passa_por_mi5_fica_numa_linha_so(self):
        # Fuyu no Hanashi médio: melodia entre Mi5 e Mi6, a regra antiga abria e fechava a cada Mi5
        alturas = [88, 84, 76, 77, 84, 88, 86, 76, 84, 88, 91, 88, 84, 77, 76, 84]
        linhas, sup = linhas_8va(alturas)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(sup, 0)

    def test_melodia_na_pauta_nao_ganha_8va(self):
        linhas, _ = linhas_8va([72, 74, 76, 77, 79, 77, 76, 74] * 2)
        self.assertEqual(len(linhas), 0)

    def test_nao_desce_nota_pra_baixo_da_pauta(self):
        # mistura Dó5 com Dó6: com 8va o Dó5 iria pro Dó4 (1 linha embaixo), sem 8va o Dó6 tem 2 em cima;
        # só vale a 8va se o total cair
        alturas = [72, 84, 72, 84, 72, 84, 72, 84]
        _, sup = linhas_8va(alturas)
        self.assertLessEqual(sup, 4 * 2)          # sem 8va: 4 Dó6 × 2 linhas = 8; nunca pior que isso
        # trecho grave com um pico só: nada de 8va (desceria tudo pra baixo da pauta)
        linhas, _ = linhas_8va([67, 69, 71, 72, 88, 72, 71, 69])
        self.assertEqual(len(linhas), 0)

    def test_verovio_desenha_uma_oitava_abaixo_do_que_soa(self):
        # bug até 2026-11-11: a nota era baixada aqui E o Verovio baixava de novo (duas oitavas)
        import re, tempfile
        from pathlib import Path
        import verovio
        alturas = [84, 86, 88, 89, 91, 89, 88, 86]          # Dó6..Sol6
        md = [(i * .5, .5, [p], None) for i, p in enumerate(alturas)]
        sc, _ = gerar.montar_partitura(md, [(0, 4, [48])], [], 100, "t", "s")
        with tempfile.TemporaryDirectory() as tmp:
            x = Path(tmp) / "x.musicxml"
            sc.write("musicxml", fp=str(x))
            texto = x.read_text(encoding="utf-8")
        self.assertIn('octave-shift', texto)
        tk = verovio.toolkit()
        tk.loadData(texto)
        notas = re.findall(r'<note [^>]*>', tk.getMEI())[:8]
        self.assertTrue(all(' oct="5"' in n and 'oct.ges="6"' in n for n in notas), notas[:2])

    def test_suplementares(self):
        self.assertEqual(gerar._suplementares(29), 1)   # Dó4
        self.assertEqual(gerar._suplementares(31), 0)   # Mi4
        self.assertEqual(gerar._suplementares(39), 0)   # Fá5
        self.assertEqual(gerar._suplementares(41), 1)   # Lá5
        self.assertEqual(gerar._suplementares(43), 2)   # Dó6


if __name__ == "__main__":
    unittest.main()
