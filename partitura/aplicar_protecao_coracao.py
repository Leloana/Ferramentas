"""Regera a música de validação com as notas/qualidades já extraídas e backup."""
import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen
import numpy as np
import gerar
from letra import buscar_letra,palavras_com_tempo
from protecao_melodia import proteger_melodia

raiz=Path(__file__).resolve().parent
base=raiz/'saida/Para Machucar Meu Coração'
with urlopen('http://127.0.0.1:8030/api/jobs',timeout=5) as resposta:
    jobs=json.load(resposta)['jobs']
if any(j['status'] in ('fila','rodando') for j in jobs):
    raise RuntimeError('A fila está ocupada. Não executar revisão ao mesmo tempo.')
dados=json.loads((raiz/'trabalho/protecao_coracao_bruta.json').read_text(encoding='utf-8'))
backup=raiz/'trabalho/protecao_20261110'/base.name
for arq in base.rglob('*'):
    if not arq.is_file() or 'cache' in arq.relative_to(base).parts or arq.name=='Original.mp3': continue
    alvo=backup/arq.relative_to(base)
    if not alvo.exists():
        alvo.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(arq,alvo)
cache=base/'cache'
registro=cache/'transcricao_protecao.json'
if registro.exists():
    dados['palavras']=json.loads(registro.read_text(encoding='utf-8'))['palavras']
else:
    oficial=buscar_letra('Para Machucar Meu Coração','João Gilberto')
    dados['palavras']=palavras_com_tempo(raiz/'trabalho/htdemucs/para_machucar_meu_coracao/vocals.wav','pt',oficial)
    registro.write_text(json.dumps(dados,ensure_ascii=False),encoding='utf-8')
grade=gerar.Grade(np.asarray(dados['bt']),dados['fase'])
args=SimpleNamespace(idioma='pt',hibrido=True,pop2piano=True,amtapc=True,estilo=1,
                     sem_transpor=False,subtitulo='Stan Getz & João Gilberto')
for nivel in ('facil','medio','dificil'):
    gerar.SR_GRADE=gerar.GRADE_NIVEL[nivel]
    protegidas,correcoes=proteger_melodia(dados['notas'],grade,nivel,dados['palavras'],dados['diagnostico'])
    if nivel=='medio':
        for a,b,p in [(31.2,31.5,54),(62.2,62.5,42)]:
            assert not any(a<=n[0]<=b and n[2]==p for n in protegidas),'Exemplo conhecido não foi protegido'
    gerar.gerar_nivel(nivel,args,raiz/'entrada/para_machucar_meu_coracao.wav',base,
        'Para Machucar Meu Coração',dados['notas'],dados['acordes'],dados['palavras'],grade,
        dados['bpm'],dados['diagnostico'])
meta_p=base/'meta.json'; meta=json.loads(meta_p.read_text(encoding='utf-8'))
meta.update(protecao_melodia='v1',atualizado=time.strftime('%Y-%m-%d %H:%M'))
meta_p.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print('[concluido] Proteção aplicada aos três níveis; backup preservado.',flush=True)
