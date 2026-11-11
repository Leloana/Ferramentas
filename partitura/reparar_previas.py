"""Refaz MIDI e MP3 a partir do MusicXML, sem modelos/GPU e sem alterar PDFs.

Uso: python reparar_previas.py "No Surprises (Radiohead)"
     python reparar_previas.py --todas [--biblioteca trabalho/outra_biblioteca] [--sem-destaque]
Com o destaque (padrão), a melodia sai mais forte que o acompanhamento (gerar.DESTAQUE).
"""
import argparse
from pathlib import Path

from gerar import midi_para_mp3, salvar_midi_notas

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta', nargs='?', help='nome da música')
    ap.add_argument('--todas', action='store_true')
    ap.add_argument('--biblioteca', type=Path, default=Path(__file__).resolve().parent / 'saida')
    ap.add_argument('--sem-destaque', action='store_true')
    ap.add_argument('--versoes', default='', help='só estes arquivos, ex.: "Acordes - Medio,HibridoAMT - Dificil"')
    a = ap.parse_args()
    pastas = (sorted(p for p in a.biblioteca.iterdir() if p.is_dir() and not p.name.startswith('pagina'))
              if a.todas else [a.biblioteca / a.pasta])
    for pasta in pastas:
        for xml in sorted((pasta / 'editaveis').glob('*.musicxml')):
            if a.versoes and xml.stem not in a.versoes.split(','):
                continue
            mid = xml.with_suffix('.mid')
            mp3 = pasta / f'{xml.stem} - previa.mp3'
            salvar_midi_notas(None, mid, xml, destaque=not a.sem_destaque)
            if mp3.exists():
                mp3.unlink()   # arquivo novo: páginas com hardlink pro antigo precisam ser refeitas
            midi_para_mp3(mid, mp3)
            print(f'[ok] {pasta.name} / {xml.stem}', flush=True)
