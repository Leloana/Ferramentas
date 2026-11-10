import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET
from music21 import stream,note,tempo,harmony
from web.partitura import renderizar
from sincronia import preparar_musicxml,notas_ligadas


class Visualizador(unittest.TestCase):
    def test_ligacoes_parciais_de_acorde(self):
        texto='''<score-partwise><part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>
        <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><tie type="start"/></note>
        <note><chord/><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration></note>
        </measure><measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><tie type="stop"/></note>
        <note><chord/><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration></note>
        </measure></part></score-partwise>'''
        _,segmentos=preparar_musicxml(texto)
        ns=notas_ligadas(segmentos)
        self.assertEqual(len(ns),3)
        self.assertEqual([(n['inicio'],n['fim']) for n in ns if n['pitch']==60],[(0,4)])

    def test_ids_tempos_e_cache(self):
        s=stream.Score()
        a=stream.Part(); b=stream.Part()
        a.insert(0,tempo.MetronomeMark(number=120))
        a.insert(2,note.Note('C4',quarterLength=2))
        a.insert(2,harmony.ChordSymbol('C'))
        b.insert(0,note.Note('C3',quarterLength=1))
        s.insert(0,a); s.insert(0,b)
        with TemporaryDirectory() as pasta:
            ed=Path(pasta)/'editaveis'; ed.mkdir()
            xml=ed/'teste.musicxml'; s.write('musicxml',fp=str(xml))
            d=renderizar(xml)
            ids={el.attrib['id'] for svg in d['paginas'] for el in ET.fromstring(svg).iter() if 'id' in el.attrib}
            self.assertTrue(d['inicios'])
            self.assertTrue(set(d['inicios']) <= ids)
            self.assertEqual(sorted(d['inicios'].values()),[0,1])
            self.assertEqual(d['quadros'][-1]['notas'],[])
            self.assertEqual(d['percurso'][0]['inicio'],0)
            self.assertEqual(d['percurso'][0]['fim'],2)
            self.assertTrue(all(m['id'] in ids for m in d['percurso']))
            self.assertEqual(d,renderizar(xml))
            primeira=d['chave']
            a.insert(6,note.Note('D4',quarterLength=1)); s.write('musicxml',fp=str(xml))
            self.assertNotEqual(primeira,renderizar(xml)['chave'])

    def test_percurso_inclui_compasso_inteiro_em_pausa(self):
        texto='''<score-partwise><part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>
        <note><rest measure="yes"/><duration>4</duration></note></measure>
        <measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
        </measure></part></score-partwise>'''
        _,ns,percurso=preparar_musicxml(texto,com_percurso=True)
        self.assertEqual(len(ns),1)
        self.assertEqual([(m['inicio'],m['fim']) for m in percurso],[(0,2),(2,4)])
        self.assertTrue(percurso[0]['pontos'][0]['pausa_compasso'])


if __name__=='__main__':
    unittest.main()
