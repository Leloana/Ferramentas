"""Tempos exatos das notas do MusicXML, compartilhados por MIDI e visualizador."""
import xml.etree.ElementTree as ET
from fractions import Fraction


def preparar_musicxml(texto, com_percurso=False):
    raiz=ET.fromstring(texto)
    segmentos=[]; andamentos={Fraction(0):120.0}; numero=0; percurso=[]
    for ip,parte in enumerate(raiz.findall('part')):
        base=Fraction(0); divisao=1; compasso=Fraction(4)
        oitava={}  # pauta -> 8va ativa (só registro: a altura do MusicXML já é a que soa)
        for im,medida in enumerate(parte.findall('measure')):
            ident_medida=f'compasso-{ip}-{im}'
            medida.set('id',ident_medida)
            pontos=[]
            cursor=Fraction(0); maior=Fraction(0); anterior=Fraction(0)
            for el in medida:
                if el.tag=='attributes':
                    divisao=int(el.findtext('divisions') or divisao)
                    tempo=el.find('time')
                    if tempo is not None and tempo.findtext('beats') and tempo.findtext('beat-type'):
                        compasso=Fraction(int(tempo.findtext('beats'))*4,int(tempo.findtext('beat-type')))
                elif el.tag in ('backup','forward'):
                    dur=Fraction(el.findtext('duration') or 0)/divisao
                    cursor+=dur if el.tag=='forward' else -dur
                    maior=max(maior,cursor)
                elif el.tag=='direction':
                    for os_ in el.iter('octave-shift'):
                        pauta=el.findtext('staff') or '1'
                        tam=int(os_.get('size') or 8)
                        salto=12*((tam-1)//7)
                        tipo=os_.get('type')
                        oitava[pauta]=salto if tipo=='down' else -salto if tipo=='up' else 0
                    sound=el.find('sound')
                    if sound is not None and sound.get('tempo'):
                        off=Fraction(el.findtext('offset') or 0)/divisao
                        andamentos[base+cursor+off]=float(sound.get('tempo'))
                elif el.tag=='note':
                    numero+=1; ident=f'nota-{numero}'; el.set('id',ident)
                    dur=Fraction(el.findtext('duration') or 0)/divisao
                    inicio=anterior if el.find('chord') is not None else cursor
                    pitch=el.find('pitch')
                    if dur>0:
                        repouso=el.find('rest')
                        pontos.append({'id':ident,'q':base+inicio,
                            'pausa_compasso':repouso is not None and repouso.get('measure')=='yes'})
                    if pitch is not None and dur>0:
                        semitons={'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
                        p=(int(pitch.findtext('octave'))+1)*12+semitons[pitch.findtext('step')]+float(pitch.findtext('alter') or 0)
                        # a altura do MusicXML já é a que soa: o octave-shift só muda o desenho (Verovio)
                        segmentos.append({'id':ident,'a':base+inicio,'b':base+inicio+dur,'pitch':int(p),
                            'voz':f'{ip}:{el.findtext("staff") or 1}:{el.findtext("voice") or 1}',
                            'letra':el.find('lyric') is not None,
                            'ataque':not any(t.get('type')=='stop' for t in el.findall('tie')),
                            'liga':any(t.get('type')=='start' for t in el.findall('tie'))})
                    maior=max(maior,inicio+dur)
                    if el.find('chord') is None:
                        anterior=inicio; cursor+=dur
            dur_medida=maior if medida.get('implicit')=='yes' else max(maior,compasso)
            if ip==0:
                percurso.append({'id':ident_medida,'a':base,'b':base+dur_medida,'pontos':pontos})
            elif im<len(percurso):
                percurso[im]['pontos']+=pontos
            base+=dur_medida
    tempos=sorted(andamentos.items())
    def segundos(q):
        total=0.0
        for i,(a,bpm) in enumerate(tempos):
            if q<=a: break
            b=tempos[i+1][0] if i+1<len(tempos) else q
            total+=float(min(q,b)-a)*60/bpm
        return total
    for s in segmentos:
        s['inicio']=segundos(s.pop('a')); s['fim']=segundos(s.pop('b'))
    if com_percurso:
        for m in percurso:
            m['inicio']=segundos(m.pop('a')); m['fim']=segundos(m.pop('b'))
            for p in m['pontos']:
                p['tempo']=segundos(p.pop('q'))
    vozes=list(raiz.iter('voice'))
    if any(v.text=='0' for v in vozes):
        for v in vozes:
            if v.text and v.text.isdigit(): v.text=str(int(v.text)+1)
    resultado=(ET.tostring(raiz,encoding='unicode'),segmentos)
    return (*resultado,percurso) if com_percurso else resultado


def notas_ligadas(segmentos):
    """Reúne ligações por nota/voz, inclusive quando só parte de um acorde liga."""
    notas=[]; abertas={}
    for s in sorted(segmentos,key=lambda s:s['inicio']):
        chave=(s['voz'],s['pitch'])
        ant=abertas.get(chave)
        if not s['ataque'] and ant is not None and abs(ant['fim']-s['inicio'])<1e-6:
            ant['fim']=s['fim']
        else:
            ant={k:s[k] for k in ('inicio','fim','pitch','voz')}
            ant['letra']=s.get('letra',False)
            notas.append(ant)
        if s['liga']: abertas[chave]=ant
        else: abertas.pop(chave,None)
    return notas
