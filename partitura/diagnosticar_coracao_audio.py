"""Confronta os pontos indicados com duas estimativas independentes da voz."""
import json
from pathlib import Path
from collections import Counter
import numpy as np
import librosa
import torch
import torchcrepe
from music21 import converter,harmony
import gerar

raiz=Path(__file__).resolve().parent
stems=raiz/'trabalho/htdemucs/para_machucar_meu_coracao'
sr=22050
mix=gerar.carregar(raiz/'entrada/para_machucar_meu_coracao.wav',sr)
voz=gerar.carregar(stems/'vocals.wav',sr)
baixo=gerar.carregar(stems/'bass.wav',sr)
resto=gerar.carregar(stems/'other.wav',sr)
bateria=gerar.carregar(stems/'drums.wav',sr)
bt,bpm=gerar.batidas(mix,sr,bateria+.5*baixo+.3*resto)
fase=gerar.fase_compasso(bt,baixo,sr); grade=gerar.Grade(bt,fase)
acs=gerar.acordes(resto+.3*baixo,baixo,sr,grade)
sc=converter.parse(str(raiz/'saida/Para Machucar Meu Coração/editaveis/Acordes - Medio.musicxml'))
kinds={v[1]:k for k,v in gerar.TIPOS.items()}
cifras=[(float(c.offset),c.root().pitchClass,kinds[c.chordKind]) for c in sc.parts[0].flatten().getElementsByClass(harmony.ChordSymbol)]
votos=Counter(round(o-j,4) for o,r,t in cifras for j,rr,tt,_ in acs if r==rr and t==tt)
delta=max(votos,key=lambda d:(votos[d],-abs(d)))
print('GRADE',float(bpm),'fase',fase,'deslocamento',delta,flush=True)
voz16=librosa.resample(voz,orig_sr=sr,target_sr=16000)
resultados=[]
for nome,centro,a,b in [('violao1',70,67,73),('violao2',166,163,169),
                      ('lar1',43,40,46),('lar2',138.5,136,141.5),
                      ('desmoronou1',50,47,53),('desmoronou2',146,143,150)]:
    ini=float(np.interp(a-delta,grade.idx,bt)); fim=float(np.interp(b-delta,grade.idx,bt))
    y=voz16[int(ini*16000):int(fim*16000)]
    f0,per=torchcrepe.predict(torch.tensor(y,dtype=torch.float32)[None],16000,160,
        fmin=65,fmax=600,model='full',decoder=torchcrepe.decode.viterbi,
        return_periodicity=True,batch_size=512,device='cuda' if torch.cuda.is_available() else 'cpu')
    f0=f0[0].cpu().numpy(); per=per[0].cpu().numpy()
    py,pv,pp=librosa.pyin(y,sr=16000,fmin=65,fmax=600,frame_length=2048,hop_length=160,
                         fill_na=np.nan)
    ts=ini+np.arange(len(f0))*.01
    pos=np.interp(ts,bt,grade.idx)+delta
    midi=librosa.hz_to_midi(f0)
    pym=librosa.hz_to_midi(py)
    print('\nTRECHO',nome,'original',round(ini,2),round(fim,2),flush=True)
    linhas=[]
    for q in np.arange(a,b,.25):
        m=(pos>=q)&(pos<q+.25); ps=midi[m]; conf=per[m]
        pyidx=np.flatnonzero(m); pyidx=pyidx[pyidx<len(pym)]
        pps=pym[pyidx]; pps=pps[np.isfinite(pps)]
        if len(ps):
            val=float(np.median(ps)); prob=float(np.median(conf))
            pval=float(np.median(pps)) if len(pps) else None
            linha=dict(beat=round(float(q),2),segundo=round(float(np.median(ts[m])),3),
                crepe_midi=round(val,2),periodicidade=round(prob,3),
                pyin_midi=round(pval,2) if pval is not None else None,
                nota=librosa.midi_to_note(round(val)),
                pyin_nota=librosa.midi_to_note(round(pval)) if pval is not None else None)
            linhas.append(linha)
            print(linha,flush=True)
    resultados.append(dict(nome=nome,inicio=ini,fim=fim,linhas=linhas))
(raiz/'trabalho/diagnostico_coracao.json').write_text(json.dumps(resultados,ensure_ascii=False,indent=2),encoding='utf-8')
