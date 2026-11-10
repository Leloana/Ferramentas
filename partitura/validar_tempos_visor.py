"""Confere se ataques do mapa SVG coincidem com os MIDIs tocados na prévia."""
from pathlib import Path
import pretty_midi
import verovio
import xml.etree.ElementTree as ET
from web.partitura import preparar_musicxml

verovio.enableLog(False)
raiz=Path(__file__).resolve().parent/'saida'
arquivos=list((raiz/'No Surprises (Radiohead)/editaveis').glob('* - Medio.musicxml'))
arquivos += [raiz/'Baby/editaveis/HibridoAMT - Medio.musicxml',
             raiz/'Garota de Ipanema/editaveis/Acordes - Medio.musicxml']
for xml in arquivos:
    tk=verovio.toolkit()
    texto,segmentos=preparar_musicxml(xml.read_text(encoding='utf-8'))
    assert tk.loadData(texto)
    classes={el.get('id'):el.get('class') for i in range(1,tk.getPageCount()+1) for el in ET.fromstring(tk.renderToSVG(i)).iter() if el.get('id')}
    pm=pretty_midi.PrettyMIDI(str(xml.with_suffix('.mid')))
    midi=[(n.start,n.pitch,n.end) for inst in pm.instruments for n in inst.notes]
    todos=list(midi)
    for s in segmentos:
        t,p=s['inicio'],s['pitch']
        assert s['id'] in classes,(xml.name,'ID ausente',s)
        matches=[(abs(a-t),i) for i,(a,q,b) in enumerate(midi) if q==p and abs(a-t)<.005]
        if matches:
            _,i=min(matches); midi.pop(i)
        else:
            assert not s['ataque'],(xml.name,'SVG sem ataque equivalente no MIDI',s)
            assert any(q==p and a<=t+.005 and b>=s['fim']-.005 for a,q,b in todos),(xml.name,'Ligação sem sustentação MIDI',s)
    assert not midi,(xml.name,'Notas do MIDI ausentes do visualizador',midi[:5])
    print('[ok] mapa SVG = ataques MIDI:',xml.parent.parent.name,xml.stem,flush=True)
