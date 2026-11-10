import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from niveis import reduzir_mao, fechar_acordes, completar_instrumentais, suavizar_baixo, simplificar_passagens


class Arranjos(unittest.TestCase):
    def test_ornamento_nao_altera_palavra(self):
        ns=[(0,.5,60),(.5,.6,61),(.6,1,60)]
        self.assertEqual(simplificar_passagens(ns)[1][2],60)
        self.assertEqual(simplificar_passagens(ns,[(.5,.6,'a')]),ns)
        self.assertEqual(simplificar_passagens([(0,.5,60),(.5,.9,61),(.9,1.5,60)])[1][2],61)

    def test_aberturas_e_classes(self):
        rng = np.random.default_rng(1)
        for mao in ('direita','esquerda'):
            for nivel in ('facil','medio','dificil'):
                ev=[(i,.5,sorted(set(rng.integers(24,96,4).tolist()))) for i in range(80)]
                out=reduzir_mao(ev,nivel,mao)
                for original,nova in zip(ev,out):
                    self.assertEqual(original[:2],nova[:2])
                    self.assertLessEqual(max(nova[2])-min(nova[2]),12)
                    self.assertTrue({p%12 for p in nova[2]} <= {p%12 for p in original[2]})
                    if mao=='direita':
                        self.assertEqual(max(original[2]),max(nova[2]))

    def test_voicing_acordes(self):
        ev=[(0,2,[36,52,58]),(2,2,[43,59,65])]
        for a,b in zip(ev,fechar_acordes(ev)):
            self.assertEqual({p%12 for p in a[2]},{p%12 for p in b[2]})
            self.assertEqual(min(a[2]),min(b[2]))
            self.assertLessEqual(max(b[2])-min(b[2]),12)

    def test_saltos(self):
        ev=[(i,.5,[36 if i%2==0 else 59]) for i in range(12)]
        out=suavizar_baixo(ev,'facil')
        self.assertLess(max(abs(b[2][0]-a[2][0]) for a,b in zip(out,out[1:])),12)
        self.assertEqual([e[2][0]%12 for e in ev],[e[2][0]%12 for e in out])

    def test_instrumental_protege_voz_e_palavras(self):
        voz=[(8,2,[72],'Hello'),(18,2,[74],'world')]
        ia=[(o,2,[76]) for o in range(0,24,2)]
        out=completar_instrumentais(voz,ia,1,[(12,16)])
        self.assertTrue(all(e in out for e in voz))
        self.assertTrue(any(e[0]==0 for e in out))
        for o,d,*_ in [e for e in out if e not in voz]:
            for a,b in [(8,10),(12,16),(18,20)]:
                self.assertFalse(o<b and o+d>a)

    def test_midi_nao_toca_cifras(self):
        from music21 import stream,note,harmony,tempo
        from gerar import salvar_midi_notas
        import pretty_midi
        s=stream.Score(); p=stream.Part()
        p.insert(0,tempo.MetronomeMark(number=120))
        p.insert(0,note.Note('C3',quarterLength=2))
        p.insert(0,harmony.ChordSymbol('C'))
        s.insert(0,p)
        with TemporaryDirectory() as pasta:
            mid=Path(pasta)/'teste.mid'
            salvar_midi_notas(s,mid)
            ns=[n for i in pretty_midi.PrettyMIDI(str(mid)).instruments for n in i.notes]
            self.assertEqual([n.pitch for n in ns],[48])
            self.assertAlmostEqual(ns[0].end-ns[0].start,1,places=3)
        self.assertEqual(len(list(s.recurse().getElementsByClass(harmony.ChordSymbol))),1)


if __name__=='__main__':
    unittest.main()
