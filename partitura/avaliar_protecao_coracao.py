"""Valida a proteção nos exemplos da gravação, sem alterar a biblioteca."""
import json
from pathlib import Path
import numpy as np
import librosa
import gerar
from protecao_melodia import proteger_melodia

raiz=Path(__file__).resolve().parent
cache=raiz/'trabalho/protecao_coracao_bruta.json'
if cache.exists():
    dados=json.loads(cache.read_text(encoding='utf-8'))
else:
    sr=22050; stems=raiz/'trabalho/htdemucs/para_machucar_meu_coracao'
    mix=gerar.carregar(raiz/'entrada/para_machucar_meu_coracao.wav',sr)
    voz=gerar.carregar(stems/'vocals.wav',sr)
    baixo=gerar.carregar(stems/'bass.wav',sr)
    resto=gerar.carregar(stems/'other.wav',sr)
    bateria=gerar.carregar(stems/'drums.wav',sr)
    bt,bpm=gerar.batidas(mix,sr,bateria+.5*baixo+.3*resto)
    fase=gerar.fase_compasso(bt,baixo,sr)
    grade=gerar.Grade(bt,fase)
    ons=librosa.onset.onset_detect(y=voz,sr=sr,units='time',backtrack=True,delta=.25)
    diag={}
    ns=gerar.melodia(librosa.resample(voz,orig_sr=sr,target_sr=16000),16000,ons,diag)
    acs=gerar.acordes(resto+.3*baixo,baixo,sr,grade)
    dados=dict(bt=bt.tolist(),bpm=float(bpm),fase=fase,notas=ns,diagnostico=diag,acordes=acs)
    cache.write_text(json.dumps(dados,ensure_ascii=False,default=lambda v:v.item()),encoding='utf-8')
grade=gerar.Grade(np.asarray(dados['bt']),dados['fase'])
for nivel in ('facil','medio','dificil'):
    gerar.SR_GRADE=gerar.GRADE_NIVEL[nivel]
    notas,c=proteger_melodia(dados['notas'],grade,nivel,diagnostico=dados['diagnostico'])
    print('\nNIVEL',nivel,'antes',len(dados['notas']),'depois',len(notas),flush=True)
    for nome,a,b in [('violao',31.1,31.8),('lar',62.1,62.9),('moronou',22.,22.6),('moronou2',65.5,66.2)]:
        print(nome,'ANTES',[(round(n[0],3),round(n[1]-n[0],3),n[2]) for n in dados['notas'] if a<=n[0]<=b],flush=True)
        print(nome,'DEPOIS',[(round(n[0],3),round(n[1]-n[0],3),n[2]) for n in notas if a<=n[0]<=b],flush=True)
        print('REMOVIDAS',[x for x in c if a<=x['inicio']<=b],flush=True)
