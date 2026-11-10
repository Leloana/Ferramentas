"""Exporta recortes A/B da biblioteca e dos backups locais, sem executar modelos.

Os arquivos prontos em exemplos/ podem ser usados sem instalar o pipeline.
Para reconstruí-los: python gerar_exemplos.py (exige biblioteca/backups locais).
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from music21 import converter, tempo, key, harmony, stream, note, chord, clef, meter, layout, metadata, pitch
import verovio
import gerar
from sincronia import preparar_musicxml, notas_ligadas
from analisar_completo import deslocamento

RAIZ=Path(__file__).resolve().parent
DESTINO=RAIZ/'exemplos'
CASOS=[
    dict(id='01-violao',titulo='Transição em meu violão',musica='Para Machucar Meu Coração',
         versao='HibridoAMT - Medio',backup='protecao_20261110',inicio=64,fim=76,
         motivo='O Sol♭/Fá♯ intermediário da subida Fá–Sol deixa de virar uma nota longa no piano.'),
    dict(id='02-nosso-lar',titulo='Ataque grave em nosso lar',musica='Para Machucar Meu Coração',
         versao='HibridoAMT - Medio',backup='protecao_20261110',inicio=132,fim=144,
         motivo='A excursão grave suspeita no ataque deixa de ser tratada como nota melódica estável.'),
    dict(id='03-desmoronou',titulo='Passagem em desmoronou',musica='Para Machucar Meu Coração',
         versao='HibridoAMT - Medio',backup='protecao_20261110',inicio=44,fim=56,
         motivo='A passagem muito breve por Lá natural deixa de receber o peso de uma colcheia inteira.'),
    dict(id='04-alcance',titulo='Acordes dentro do alcance',musica='Garota de Ipanema',
         versao='Acordes - Medio',backup='revisao_20261109',inicio=None,fim=None,
         motivo='Notas do acompanhamento são reposicionadas por oitavas para diminuir a abertura da mão esquerda.'),
    dict(id='05-introducao',titulo='Introdução instrumental',musica='No Surprises (Radiohead)',
         versao='HibridoAMT - Medio',backup='revisao_20261109',inicio=0,fim=24,
         motivo='O Híbrido recebe notas da direita instrumental que eram descartadas antes da entrada da voz.'),
]


def carregar(xml):
    sc=converter.parse(str(xml))
    bpm=float(list(sc.flatten().getElementsByClass(tempo.MetronomeMark))[0].getQuarterBPM())
    texto,segmentos=preparar_musicxml(xml.read_text(encoding='utf-8'))
    elementos={el.get('id'):el for el in ET.fromstring(texto).iter('note')}
    letras={}
    for s in segmentos:
        ly=elementos[s['id']].find('lyric')
        if ly is not None:
            txt=ly.findtext('text') or ''
            sil=ly.findtext('syllabic')
            letras[(s['voz'],s['pitch'],s['inicio'])]={'begin':f'{txt}-','middle':f'-{txt}-','end':f'-{txt}'}.get(sil,txt)
    ns=notas_ligadas(segmentos)
    varias_partes=any(int(n['voz'].split(':')[0])>0 for n in ns)
    maos=[[],[]]
    for n in ns:
        voz=n['voz'].split(':')
        mao=int(voz[0]) if varias_partes else int(voz[1])-1
        if mao<2:
            maos[mao].append(dict(inicio=n['inicio']*bpm/60,fim=n['fim']*bpm/60,pitch=n['pitch'],
                letra=letras.get((n['voz'],n['pitch'],n['inicio']))))
    plana=sc.parts[0].flatten()
    cifras=[(float(c.offset),{p.pitchClass for p in c.pitches},deepcopy(c)) for c in plana.getElementsByClass(harmony.ChordSymbol)]
    armaduras=[(float(k.offset),k.sharps) for k in plana.getElementsByClass(key.KeySignature)]
    return dict(maos=maos,bpm=bpm,cifras=cifras,armaduras=armaduras)


def recortar(dados,inicio,fim,delta=0):
    maos=[[],[]]
    for i,ns in enumerate(dados['maos']):
        for n in ns:
            a=max(inicio,n['inicio']+delta); b=min(fim,n['fim']+delta)
            if b>a+1e-6:
                maos[i].append(dict(inicio=round(a-inicio,6),fim=round(b-inicio,6),pitch=n['pitch'],
                    letra=n['letra'] if n['inicio']+delta>=inicio-1e-6 else None))
    return maos


def estatisticas(maos):
    resultado={}
    for nome,ns in zip(('direita','esquerda'),maos):
        aberturas=[]
        for t in sorted({n['inicio'] for n in ns}):
            ps={n['pitch'] for n in ns if n['inicio']<=t+1e-7 and n['fim']>t+1e-7}
            if len(ps)>1: aberturas.append(max(ps)-min(ps))
        resultado[nome]=dict(notas=len(ns),abertura_max_semitons=max(aberturas,default=0),
            aberturas_maiores_oitava=sum(a>12 for a in aberturas),
            ataques_polifonicos=len(aberturas))
    return resultado


def montar(maos,dados,caso,versao,armadura,delta):
    sc=stream.Score(); sc.metadata=metadata.Metadata()
    sc.metadata.title=caso['titulo']+' — '+versao
    sc.metadata.composer=caso['versao']+' · recorte automatizado'
    dur=caso['fim']-caso['inicio']
    for i,ns in enumerate(maos):
        p=stream.PartStaff(id=f'mao{i}')
        p.insert(0,clef.TrebleClef() if i==0 else clef.BassClef())
        p.insert(0,meter.TimeSignature('4/4')); p.insert(0,key.KeySignature(armadura))
        if i==0:p.insert(0,tempo.MetronomeMark(number=dados['bpm']))
        grupos=defaultdict(list)
        for n in ns: grupos[(n['inicio'],round(n['fim']-n['inicio'],6),n['letra'])].append(n['pitch'])
        for (a,d,txt),ps in sorted(grupos.items(),key=lambda item:item[0][0]):
            alturas=[]
            for midi in sorted(ps):
                nomes=gerar.NOMES_PC_BEMOL if armadura<0 else gerar.NOMES_PC_SUST
                q=pitch.Pitch(nomes[midi%12]); q.octave=midi//12-1
                alturas.append(q)
            el=note.Note(alturas[0]) if len(alturas)==1 else chord.Chord(alturas)
            el.quarterLength=d
            if txt:el.addLyric(txt)
            p.insert(a,el)
        p.makeRests(refStreamOrTimeRange=(0,dur),fillGaps=True,inPlace=True)
        sc.insert(0,p)
    sc.insert(0,layout.StaffGroup(list(sc.parts),symbol='brace',barTogether=True))
    sc=sc.makeNotation()
    # Inserir cifras depois de preencher pausas conserva os tempos do recorte.
    selecionadas=[(o+delta,c) for o,_,c in dados['cifras'] if o+delta<caso['fim']]
    anteriores=[c for o,c in selecionadas if o<=caso['inicio']]
    figuras=([(0,anteriores[-1])] if anteriores else [])+[(o-caso['inicio'],c) for o,c in selecionadas if o>caso['inicio']]
    medidas=list(sc.parts[0].getElementsByClass(stream.Measure))
    for off,c in figuras:
        candidatas=[m for m in medidas if float(m.offset)<=off+1e-7]
        if candidatas:
            m=candidatas[-1]; m.insert(off-float(m.offset),deepcopy(c))
    return sc


def svg_compacto(xml,destino):
    verovio.enableLog(False); tk=verovio.toolkit()
    tk.setResourcePath(str(Path(verovio.__file__).parent/'data'))
    tk.setOptions(dict(pageWidth=2100,pageHeight=2200,scale=45,pageMarginTop=50,
                       pageMarginLeft=60,pageMarginRight=60,pageMarginBottom=50,
                       adjustPageHeight=True,footer='none',breaks='auto'))
    assert tk.loadData(gerar.xml_para_verovio(xml.read_text(encoding='utf-8')))
    assert tk.getPageCount()==1,'Reduzir recorte: a prévia deve caber em uma página'
    svg=ET.fromstring(gerar._desembaralhar(tk.renderToSVG(1)))
    ET.register_namespace('','http://www.w3.org/2000/svg')
    ET.register_namespace('xlink','http://www.w3.org/1999/xlink')
    svg.insert(0,ET.Element('{http://www.w3.org/2000/svg}rect',dict(x='0',y='0',width='100%',height='100%',fill='white')))
    destino.write_text(ET.tostring(svg,encoding='unicode'),encoding='utf-8')


def main():
    manifesto=dict(gerado_em=datetime.now().astimezone().isoformat(timespec='seconds'),
        descricao='Recortes de arranjos automáticos; áudios sintetizados novamente com o mesmo piano.',casos=[])
    for configuracao in CASOS:
        caso=dict(configuracao)
        nome=caso['versao']+'.musicxml'
        antes_path=RAIZ/'trabalho'/caso['backup']/caso['musica']/'editaveis'/nome
        depois_path=RAIZ/'saida'/caso['musica']/'editaveis'/nome
        if not antes_path.exists() or not depois_path.exists():
            raise FileNotFoundError(f'Biblioteca/backups locais necessários para reconstruir {caso["id"]}. Os exemplos prontos já estão em exemplos/.')
        antes=carregar(antes_path); depois=carregar(depois_path)
        delta=deslocamento([(o,pcs) for o,pcs,_ in antes['cifras']],[(o,pcs) for o,pcs,_ in depois['cifras']])
        assert abs(antes['bpm']-depois['bpm'])<.001,'Comparar com o mesmo andamento'
        if caso['inicio'] is None:
            candidato=next(n['inicio']+delta for n in antes['maos'][1]
                if max(p['pitch'] for p in antes['maos'][1] if abs(p['inicio']-n['inicio'])<1e-7)
                 -min(p['pitch'] for p in antes['maos'][1] if abs(p['inicio']-n['inicio'])<1e-7)>12)
            caso['inicio']=int(candidato//4)*4; caso['fim']=caso['inicio']+16
        pasta=DESTINO/caso['id']; pasta.mkdir(parents=True,exist_ok=True)
        arm=[s for o,s in depois['armaduras'] if o<=caso['inicio']]
        armadura=arm[-1] if arm else 0
        caso.update(bpm=depois['bpm'],duracao_musical_s=(caso['fim']-caso['inicio'])*60/depois['bpm'],
                    deslocamento_antes=delta,armadura_sustenidos=armadura,
                    fonte_antes=str(antes_path.relative_to(RAIZ)),fonte_depois=str(depois_path.relative_to(RAIZ)),arquivos={})
        for versao,dados,ajuste in [('antes',antes,delta),('depois',depois,0)]:
            maos=recortar(dados,caso['inicio'],caso['fim'],ajuste)
            sc=montar(maos,dados,caso,versao,armadura,ajuste)
            xml=pasta/f'{versao}.musicxml'; mid=pasta/f'{versao}.mid'; mp3=pasta/f'{versao}.mp3'
            sc.write('musicxml',fp=str(xml)); gerar.salvar_midi_notas(sc,mid,xml)
            gerar.xml_para_pdf(xml,pasta/f'{versao}.pdf'); svg_compacto(xml,pasta/f'{versao}.svg')
            gerar.midi_para_mp3(mid,mp3)
            # Mesmo silêncio final nos dois lados facilita repetir a comparação.
            temporario=pasta/f'{versao}.temporario.mp3'
            subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(mp3),'-af','apad',
                '-t',str(caso['duracao_musical_s']+1),'-b:a','192k',str(temporario)],check=True)
            temporario.replace(mp3)
            caso[versao]=estatisticas(maos)
            for ext in ('musicxml','mid','mp3','pdf','svg'):
                arq=pasta/f'{versao}.{ext}'
                caso['arquivos'][arq.name]=dict(bytes=arq.stat().st_size,sha256=hashlib.sha256(arq.read_bytes()).hexdigest())
            print('[ok]',caso['id'],versao,caso[versao],flush=True)
        (pasta/'comparacao.json').write_text(json.dumps(caso,ensure_ascii=False,indent=2),encoding='utf-8')
        manifesto['casos'].append(caso)
    DESTINO.mkdir(exist_ok=True)
    (DESTINO/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[concluido] Cinco comparações exportadas.',flush=True)


if __name__=='__main__':main()
