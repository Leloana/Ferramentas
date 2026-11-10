"""Partitura acompanhando a gravação original: batidas da gravação + deslocamento da versão."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

import gerar


class GradeFalsa:
    def __init__(self):
        # gravação que acelera: 0,6 s por tempo e depois 0,45; tempo 0 na batida 3
        self.bt = np.concatenate([np.arange(0, 6, .6), 6 + np.arange(1, 40) * .45])
        self.idx = np.arange(len(self.bt), dtype=float) - 3

    def pos(self, t):
        return float(np.interp(t, self.bt, self.idx))


class SincroniaOriginal(unittest.TestCase):
    def test_nota_cai_no_segundo_certo_do_original(self):
        from web.partitura import renderizar
        grade = GradeFalsa()
        # melodia começando no tempo 1 (anacruse): a partitura desloca pra começar no compasso
        md = [(1.0 + i, 1, [60 + i % 5], None) for i in range(12)]
        me = [(4.0 * k, 4, [48]) for k in range(4)]
        sc, _ = gerar.montar_partitura(md, me, [], 120, "t", "s")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "editaveis").mkdir()
            xml = base / "editaveis" / "Acordes - Medio.musicxml"
            sc.write("musicxml", fp=str(xml))
            gerar.registrar_sincronia(base, "Acordes - Medio", grade, gerar.deslocamento(md, me))
            r = renderizar(xml)
        mapa = r["original"]
        self.assertIsNotNone(mapa)
        inicios = sorted(set(r["inicios"].values()))
        for off, _, _, _ in md:  # cada nota da melodia
            t_original = float(np.interp(off, grade.idx, grade.bt))
            s = (off + mapa["desloc"]) * 60 / mapa["bpm"]  # segundos na partitura
            self.assertTrue(any(abs(s - x) < 1e-3 for x in inicios), (off, s))
            volta = float(np.interp(s * mapa["bpm"] / 60 - mapa["desloc"], mapa["idx"], mapa["bt"]))
            self.assertAlmostEqual(volta, t_original, places=3)

    def test_geracao_antiga_sem_mapa(self):
        from web.partitura import mapa_original
        self.assertIsNone(mapa_original(Path("/nao/existe.json"), "Acordes - Medio", "<score-partwise/>"))


if __name__ == "__main__":
    unittest.main()
