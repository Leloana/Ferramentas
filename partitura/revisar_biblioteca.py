"""Aplica revisão de tocabilidade aos MusicXML, preservando originais em trabalho/.

Não executa modelos. Reconstrói acompanhamento e introduções a partir das versões
existentes. Nos arquivos antigos sem tempos de palavras, completa apenas intro/outro.
Uso: python revisar_biblioteca.py [nome da pasta]
"""
import json
import shutil
import sys
from pathlib import Path
from music21 import converter, harmony, tempo, note
from gerar import TIPOS, montar_partitura, salvar_versao
from niveis import (reduzir_mao, fechar_acordes, suavizar_baixo,
                    completar_instrumentais, mao_esquerda_acordes, GRADE)
from analisar_completo import deslocamento

RAIZ = Path(__file__).resolve().parent
REVISAO = 'tocabilidade-v1'


def backup(pasta):
    destino = RAIZ/'trabalho/revisao_20261109'/pasta.name
    destino.mkdir(parents=True, exist_ok=True)
    for arq in pasta.rglob('*'):
        if not arq.is_file() or 'cache' in arq.relative_to(pasta).parts or arq.name=='Original.mp3':
            continue
        alvo=destino/arq.relative_to(pasta)
        if not alvo.exists():
            alvo.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(arq,alvo)
    return destino


def ler(arq):
    sc=converter.parse(str(arq))
    maos=[]
    for parte in list(sc.parts)[:2]:
        ev=[]
        for n in parte.stripTies().flatten().notes:
            if isinstance(n,harmony.ChordSymbol):
                continue
            texto=None
            if isinstance(n,note.Note) and n.lyrics:
                ly=n.lyrics[0]
                texto={'begin':f'{ly.text}-','middle':f'-{ly.text}-','end':f'-{ly.text}'}.get(ly.syllabic,ly.text)
            ev.append((float(n.offset),float(n.quarterLength),[p.midi for p in n.pitches],texto))
        maos.append(sorted(ev,key=lambda e:e[0]))
    cifras=[]
    kinds={valor[1]:tipo for tipo,valor in TIPOS.items()}
    for cs in sc.parts[0].flatten().getElementsByClass(harmony.ChordSymbol):
        if cs.chordKind not in kinds:
            raise ValueError(f'Cifra não suportada: {cs.chordKind}')
        cifras.append((float(cs.offset),cs.root().pitchClass,kinds[cs.chordKind]))
    bpm=float(list(sc.flatten().getElementsByClass(tempo.MetronomeMark))[0].getQuarterBPM())
    return sc,maos,sorted(cifras),bpm


def assinatura_cifras(cifras):
    return [(o,{(r+i)%12 for i in TIPOS[t][0]}) for o,r,t in cifras]


def revisar(pasta):
    meta_p=pasta/'meta.json'
    meta=json.loads(meta_p.read_text(encoding='utf-8')) if meta_p.exists() else {}
    if meta.get('revisao_partituras')==REVISAO:
        print(f'[skip] {pasta.name}: já revisada',flush=True)
        return
    orig=backup(pasta)
    dados={arq.stem:ler(arq) for arq in (orig/'editaveis').glob('*.musicxml')}
    if not dados:
        return
    for nome,(sc,maos,cifras,bpm) in sorted(dados.items()):
        versao,nome_nivel=nome.split(' - ')
        nivel=nome_nivel.lower()
        md,me=maos
        if versao=='Acordes':
            if nivel=='medio':
                novo=[]
                for o,d,ps,*_ in me:
                    vigentes=[(a,r,t) for a,r,t in cifras if a<=o+1e-7]
                    if vigentes:
                        _,r,t=vigentes[-1]
                        novo+=mao_esquerda_acordes([(o,r,t,None)],nivel,o+d,TIPOS,janela=d)
                    else:
                        novo.append((o,d,ps))
                me=novo
            me=suavizar_baixo(fechar_acordes(me),nivel)
        else:
            me=reduzir_mao(me,nivel,'esquerda')
            if versao in ('Hibrido','HibridoAMT'):
                fonte=('AMT-APC' if versao=='HibridoAMT' else 'Pop2Piano')+' - '+nome_nivel
                if fonte in dados:
                    _,maos_ia,cifras_ia,_=dados[fonte]
                    delta=deslocamento(assinatura_cifras(cifras_ia),assinatura_cifras(cifras))
                    ia=[(o+delta,d,ps) for o,d,ps,*_ in reduzir_mao(maos_ia[0],nivel,'direita')]
                    # Arquivos antigos não têm os tempos originais do Whisper.
                    # Proteger toda a região cantada para não preencher palavras perdidas.
                    bloqueios=[(min(o for o,*_ in md),max(o+d for o,d,*_ in md))] if md else []
                    antes=len(md)
                    md=completar_instrumentais(md,ia,1/GRADE[nivel],bloqueios)
                    print(f'[instrumental] {pasta.name} / {nome}: +{len(md)-antes}',flush=True)
            else:
                md=reduzir_mao(md,nivel,'direita')
        nova,_=montar_partitura(md,me,cifras,bpm,
             sc.metadata.title or pasta.name,sc.metadata.composer or '',uma_armadura=nivel=='facil')
        salvar_versao(nova,pasta,nome)
        print(f'[revisado] {pasta.name} / {nome}',flush=True)
    meta['revisao_partituras']=REVISAO
    meta_p.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    pastas=[RAIZ/'saida'/sys.argv[1]] if len(sys.argv)>1 else sorted((RAIZ/'saida').iterdir())
    for pasta in pastas:
        if pasta.is_dir():
            revisar(pasta)
