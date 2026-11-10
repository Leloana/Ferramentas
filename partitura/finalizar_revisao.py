"""Atualiza MIDI por nota ligada e refaz apenas prévias cujo conteúdo mudou.

Cada música tem um trabalhador próprio para não compartilhar arquivos temporários.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pretty_midi
from gerar import salvar_midi_notas,midi_para_mp3,xml_para_pdf

RAIZ=Path(__file__).resolve().parent


def assinatura(mid):
    return sorted((n.pitch,n.start,n.end,n.velocity) for inst in pretty_midi.PrettyMIDI(str(mid)).instruments for n in inst.notes)


def finalizar(pasta):
    alteradas=0
    for xml in sorted((pasta/'editaveis').glob('*.musicxml')):
        mid=xml.with_suffix('.mid')
        antes=assinatura(mid)
        salvar_midi_notas(None,mid,xml)
        depois=assinatura(mid)
        mudou=len(antes)!=len(depois) or any(a[0]!=b[0] or abs(a[1]-b[1])>.005 or abs(a[2]-b[2])>.005 or a[3]!=b[3] for a,b in zip(antes,depois))
        if mudou:
            midi_para_mp3(mid,pasta/f'{xml.stem} - previa.mp3')
            alteradas+=1
        xml_para_pdf(xml,pasta/f'{xml.stem}.pdf')
        print(f'[conferido] {pasta.name} / {xml.stem}: '+('áudio atualizado' if mudou else 'áudio já confere'),flush=True)
    print(f'[finalizado] {pasta.name}: {alteradas} prévias atualizadas',flush=True)


if __name__=='__main__':
    pastas=[p for p in sorted((RAIZ/'saida').iterdir()) if (p/'editaveis').exists()]
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(finalizar,pastas))
