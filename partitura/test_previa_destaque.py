"""Prévia com a melodia em destaque: nota cantada mais forte que o acompanhamento."""
import tempfile
import unittest
from pathlib import Path

import gerar


class Destaque(unittest.TestCase):
    def test_cantada_mais_forte_que_esquerda(self):
        import pretty_midi
        md = [(0, 1, [72], "la"), (1, 1, [74], "le"), (2, 2, [76, 79])]
        me = [(0, 2, [48, 52, 55]), (2, 2, [43, 47])]
        sc, _ = gerar.montar_partitura(md, me, [], 100, "t", "s")
        with tempfile.TemporaryDirectory() as d:
            xml, mid = Path(d) / "t.musicxml", Path(d) / "t.mid"
            sc.write("musicxml", fp=str(xml))
            gerar.salvar_midi_notas(sc, mid, xml)
            notas = [n for i in pretty_midi.PrettyMIDI(str(mid)).instruments for n in i.notes]
            vel = {n.pitch: n.velocity for n in notas}
            self.assertGreater(vel[72], vel[48])
            self.assertGreater(vel[79], vel[76])      # nota de cima da direita sem letra
            gerar.salvar_midi_notas(sc, mid, xml, destaque=False)
            planas = {n.velocity for i in pretty_midi.PrettyMIDI(str(mid)).instruments for n in i.notes}
            self.assertEqual(len(planas), 1)


if __name__ == "__main__":
    unittest.main()
