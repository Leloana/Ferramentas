"""Refaz MIDI e MP3 a partir do MusicXML, sem modelos/GPU e sem alterar PDFs.

Uso: python reparar_previas.py "No Surprises (Radiohead)"
     python reparar_previas.py --todas
"""
import sys
from pathlib import Path
from gerar import salvar_midi_notas, midi_para_mp3

if __name__ == '__main__':
    saida = Path(__file__).resolve().parent / 'saida'
    if len(sys.argv) != 2:
        raise SystemExit('Informe o nome da pasta ou --todas')
    pastas = sorted(saida.iterdir()) if sys.argv[1] == '--todas' else [saida / sys.argv[1]]
    for pasta in pastas:
        for xml in sorted((pasta/'editaveis').glob('*.musicxml')):
            mid = xml.with_suffix('.mid')
            salvar_midi_notas(None, mid, xml)
            midi_para_mp3(mid, pasta / f'{xml.stem} - previa.mp3')
            print(f'[ok] {pasta.name} / {xml.stem}', flush=True)
