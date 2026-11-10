"""Atualiza No Surprises com o pipeline e revisa o restante sem executar IAs."""
import json
import subprocess
import sys
from pathlib import Path
from revisar_biblioteca import backup, revisar, REVISAO

RAIZ=Path(__file__).resolve().parent

if __name__=='__main__':
    pasta=RAIZ/'saida/No Surprises (Radiohead)'
    backup(pasta)
    # Reexecutar esta música preserva os tempos originais das palavras e permite
    # completar também interlúdios, além de exportar o Pop2Piano completo ausente.
    subprocess.run([sys.executable,'-u','-X','utf8','gerar.py',
        str(RAIZ/'entrada/no_surprises_LBt60dfwEBY.wav'),
        '--titulo','No Surprises','--artista','Radiohead','--subtitulo','Radiohead',
        '--pasta',pasta.name,'--nivel','todos','--hibrido','--pop2piano','--amtapc',
        '--idioma','en'],cwd=RAIZ,check=True)
    meta_p=pasta/'meta.json'
    meta=json.loads(meta_p.read_text(encoding='utf-8'))
    meta.update(revisao_partituras=REVISAO,estilo_pop2piano=1)
    meta_p.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    for outra in sorted((RAIZ/'saida').iterdir()):
        if outra.is_dir() and outra!=pasta:
            revisar(outra)
    print('[concluido] Biblioteca revisada',flush=True)
