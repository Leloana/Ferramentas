"""Confere alturas, ataques e durações escritos contra os MIDIs das prévias."""
from pathlib import Path
import argparse
import pretty_midi
from sincronia import preparar_musicxml,notas_ligadas

saida=Path(__file__).resolve().parent/'saida'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--todas',action='store_true')
parser.add_argument('--pasta',default='No Surprises (Radiohead)')
args=parser.parse_args()
arquivos=sorted(saida.glob('*/editaveis/*.musicxml')) if args.todas else sorted((saida/args.pasta/'editaveis').glob('*.musicxml'))
total=0
for xml in arquivos:
    _,segmentos=preparar_musicxml(xml.read_text(encoding='utf-8'))
    esperado=notas_ligadas(segmentos)
    pm=pretty_midi.PrettyMIDI(str(xml.with_suffix('.mid')))
    real=[(n.start,n.end,n.pitch) for inst in pm.instruments for n in inst.notes]
    assert len(esperado)==len(real),(xml.name,'contagem',len(esperado),len(real))
    for n in esperado:
        matches=[(abs(a-n['inicio'])+abs(b-n['fim']),i) for i,(a,b,p) in enumerate(real)
                 if p==n['pitch'] and abs(a-n['inicio'])<.005 and abs(b-n['fim'])<.005]
        assert matches,(xml.name,'nota diferente',n)
        _,i=min(matches); real.pop(i)
    total+=len(esperado)
    print('[ok]',xml.parent.parent.name,xml.stem,len(esperado),'notas',flush=True)
print(f'Conferidos {len(arquivos)} MIDIs e {total} notas, sem diferenças de altura, ataque ou duração.',flush=True)
