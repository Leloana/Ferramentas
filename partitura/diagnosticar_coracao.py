"""Localiza versos/notas para comparar a transcrição com a gravação original."""
from pathlib import Path
from music21 import converter,harmony,note,tempo

RAIZ=Path(__file__).resolve().parent
for nivel in ('Facil','Medio','Dificil'):
    p=RAIZ/'saida/Para Machucar Meu Coração/editaveis'/f'HibridoAMT - {nivel}.musicxml'
    sc=converter.parse(str(p)); md=sc.parts[0]
    bpm=list(sc.flatten().getElementsByClass(tempo.MetronomeMark))[0].number
    ev=[]
    for n in md.flatten().notes:
        if isinstance(n,harmony.ChordSymbol) or not isinstance(n,note.Note):continue
        if n.tie and n.tie.type in ('continue','stop'):continue
        ev.append((float(n.offset),float(n.quarterLength),n.pitch.nameWithOctave,n.lyric or '',n.measureNumber))
    print('\nNIVEL',nivel,'BPM',bpm,flush=True)
    for i,e in enumerate(ev):
        texto=e[3].lower()
        if any(s in texto for s in ('vio','lão','lao','lar','des','mo','rou','nou')):
            print('ALVO',i,ev[max(0,i-3):i+5],flush=True)
