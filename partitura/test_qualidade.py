"""Testes das peças do teste em massa (2026-11-11): grafia pela escala, cache do modo leve, dinâmica,
métricas de leitura (qualidade.py) e os ajustes de parâmetros do lote.py."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np


class TestGrafiaDaEscala(unittest.TestCase):
    def test_escalas(self):
        import gerar
        self.assertEqual(gerar.grafia_da_escala(0)[6] if 6 in gerar.grafia_da_escala(0) else None, None)
        self.assertEqual(gerar.grafia_da_escala(5)[3], "D#")      # Ré♯ em Si maior, nunca Mi♭
        self.assertEqual(gerar.grafia_da_escala(5)[8], "G#")
        self.assertEqual(gerar.grafia_da_escala(6)[5], "E#")      # Mi♯ em Fá♯ maior
        self.assertEqual(gerar.grafia_da_escala(-6)[11], "C-")    # Dó♭ em Sol♭ maior
        self.assertEqual(gerar.grafia_da_escala(-3)[8], "A-")

    def test_partitura_sem_enarmonia_evitavel(self):
        """Acorde mal detectado (Sol♯maj7 num trecho de Si maior) não leva as notas da escala pra Lá♭/Mi♭."""
        import gerar
        import qualidade
        md = [(float(i), 1.0, [p]) for i, p in enumerate([68, 71, 75, 73, 71, 68, 66, 68])]   # G# B D# C# B G# F# G#
        me = [(0.0, 4.0, [44, 51]), (4.0, 4.0, [47, 54])]
        cifras = [(0.0, 8, "maj7"), (4.0, 11, "maj")]
        sc, _ = gerar.montar_partitura(md, me, cifras, 100, "t", "s")
        with tempfile.TemporaryDirectory() as d:
            xml = Path(d) / "t.musicxml"
            sc.write("musicxml", fp=str(xml))
            r = qualidade.leitura(xml.read_text(encoding="utf-8"))
        self.assertEqual(r["evitaveis_por_100"], 0)


class TestCacheLeve(unittest.TestCase):
    def test_cache_do_leve_e_reaproveitado(self):
        import gerar
        with tempfile.TemporaryDirectory() as d:
            base, audio = Path(d), Path(d) / "a.wav"
            audio.write_bytes(b"x" * 10)
            (base / "cache").mkdir()
            st = audio.stat()
            (base / "cache" / "transcricao.json").write_text(json.dumps(dict(
                audio_tamanho=st.st_size, audio_mtime_ns=st.st_mtime_ns, notas=[], acordes=[[0, 0, "maj", 0]],
                leve=True, bt=[0, 1], fase=0, bpm=60)), encoding="utf-8")
            self.assertIsNotNone(gerar.carregar_transcricao(base, audio))


class TestDinamica(unittest.TestCase):
    def test_estrofe_e_refrao(self):
        import dinamica
        intens = [(k, -20.0) for k in range(8)] + [(k, -12.0) for k in range(8, 16)] + [(k, -20.0) for k in range(16, 24)]
        trocas = dinamica.niveis_por_compasso(intens)
        niveis = dict(trocas)
        self.assertEqual(trocas[0][0], 0)
        self.assertIn(8, niveis)
        self.assertIn(16, niveis)
        ordem = "p mp mf f".split()
        self.assertGreater(ordem.index(niveis[8]), ordem.index(niveis[0]))

    def test_musica_plana_num_nivel_so(self):
        import dinamica
        intens = [(k, -15.0 + 0.1 * (k % 2)) for k in range(30)]
        self.assertEqual(dinamica.niveis_por_compasso(intens), [(0, "mf")])

    def test_trecho_minimo(self):
        import dinamica
        intens = [(k, -20.0) for k in range(10)] + [(10, -8.0)] + [(k, -20.0) for k in range(11, 20)]
        trocas = dinamica.niveis_por_compasso(intens)
        ks = [k for k, _ in trocas]
        self.assertTrue(all(b - a >= dinamica.MIN_COMPASSOS for a, b in zip(ks, ks[1:])))


class TestQualidade(unittest.TestCase):
    def test_tocabilidade_e_som(self):
        import qualidade
        md = [(0.0, 1.0, [72]), (1.0, 1.0, [61]), (2.0, 1.0, [59])]
        me = [(0.0, 3.0, [60])]
        t = qualidade.tocabilidade(md, me, 120)
        self.assertEqual(t["maos_cruzadas"], 1)          # Si3 da direita abaixo do Dó4 da esquerda
        s = qualidade.som(md, me, [[0, 0, "maj", 0]], 0.0, {"maj": ([0, 4, 7], "", "")})
        self.assertGreater(s["choques_por_100"], 0)      # Dó♯ contra Dó: 2ª menor

    def test_casar(self):
        import qualidade
        self.assertEqual(qualidade._casar([(0.0, 60), (1.0, 62)], [(0.1, 60), (1.5, 62)], .15), 1)


class TestAjustesDoLote(unittest.TestCase):
    def test_constante_e_padrao_de_funcao(self):
        import derivados
        import lote
        import niveis
        antes_dif, antes_grave, antes_f = dict(derivados.DIFICIL), niveis.GRAVE_MINIMO, derivados._nota_do_acorde_abaixo
        try:
            lote.aplicar_ajustes({"derivados.DIFICIL": {"tercas": False}, "niveis.GRAVE_MINIMO": 36,
                                  "derivados._nota_do_acorde_abaixo.alvo": 3})
            self.assertFalse(derivados.DIFICIL["tercas"])
            self.assertTrue(derivados.DIFICIL["arpejo"])
            self.assertEqual(niveis.GRAVE_MINIMO, 36)
            self.assertEqual(derivados._nota_do_acorde_abaixo(72, {0, 4, 7}), 69 - 2)   # Mi4 a 5 semitons? alvo 3
        finally:
            derivados.DIFICIL, niveis.GRAVE_MINIMO, derivados._nota_do_acorde_abaixo = antes_dif, antes_grave, antes_f


class TestDificilSemChoque(unittest.TestCase):
    def test_arpejo_nao_choca_com_a_melodia(self):
        import derivados
        import gerar
        antes = dict(derivados.DIFICIL)
        try:
            derivados.DIFICIL["evitar_choque"] = True
            md = [(0.0, 4.0, [77])]                       # Fá5 segurado
            me = [(0.0, 4.0, [48])]                       # Dó3: arpejo Dó-Mi-Sol-Dó
            _, esq, _ = derivados.dificil_de_medio(md, me, [[0, 0, "maj", 0]], gerar.TIPOS, 100)
            self.assertFalse(any((77 - p) % 12 == 1 for _, _, ps in esq for p in ps))   # nenhum Mi contra o Fá
        finally:
            derivados.DIFICIL = antes


if __name__ == "__main__":
    unittest.main()


class TestAndamento(unittest.TestCase):
    def test_periodo_entre_quadros(self):
        """126 bpm com batidas presas a quadros de 23,2 ms: a mediana cai num valor fixo (123,05); a média acerta."""
        import gerar
        quadro = 512 / 22050
        bt = np.round(np.arange(200) * (60 / 126) / quadro) * quadro
        self.assertAlmostEqual(60 / float(np.median(np.diff(bt))), 123.05, delta=.1)
        self.assertAlmostEqual(60 / gerar.periodo_das_batidas(bt), 126, delta=.3)

    def test_ignora_batida_perdida(self):
        import gerar
        bt = list(np.arange(50) * .5)
        del bt[20]                                   # uma batida perdida (intervalo dobrado)
        self.assertAlmostEqual(gerar.periodo_das_batidas(bt), .5, places=3)
