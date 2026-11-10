"""Confere integridade, notas e áudio dos exemplos prontos para publicação."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import pretty_midi
from sincronia import preparar_musicxml,notas_ligadas

raiz=Path(__file__).resolve().parent/'exemplos'
manifesto=json.loads((raiz/'manifesto.json').read_text(encoding='utf-8'))
notas_total=0
for caso in manifesto['casos']:
    pasta=raiz/caso['id']
    for nome,metadados in caso['arquivos'].items():
        conteudo=(pasta/nome).read_bytes()
        assert len(conteudo)==metadados['bytes'],nome
        assert hashlib.sha256(conteudo).hexdigest()==metadados['sha256'],nome
    duracoes=[]
    notas_lado={}
    for versao in ('antes','depois'):
        xml=pasta/f'{versao}.musicxml'
        _,segmentos=preparar_musicxml(xml.read_text(encoding='utf-8'))
        ns=notas_ligadas(segmentos)
        pm=pretty_midi.PrettyMIDI(str(pasta/f'{versao}.mid'))
        reais=[n for inst in pm.instruments for n in inst.notes]
        assert len(reais)==len(ns)==sum(caso[versao][mao]['notas'] for mao in ('direita','esquerda'))
        notas_lado[versao]={(round(n['inicio'],3),round(n['fim'],3),n['pitch']) for n in ns}
        notas_total+=len(ns)
        for n in ns:
            candidatos=[(abs(r.start-n['inicio'])+abs(r.end-n['fim']),i) for i,r in enumerate(reais)
                if r.pitch==n['pitch'] and abs(r.start-n['inicio'])<.005 and abs(r.end-n['fim'])<.005]
            assert candidatos,(caso['id'],versao,n)
            _,i=min(candidatos);reais.pop(i)
        assert (pasta/f'{versao}.pdf').read_bytes().startswith(b'%PDF')
        svg=ET.fromstring((pasta/f'{versao}.svg').read_text(encoding='utf-8'))
        assert svg[0].get('fill')=='white','Prévia ilegível no tema escuro'
        mp3=pasta/f'{versao}.mp3'
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
            'format=duration:stream=codec_name','-of','json',str(mp3)],text=True))
        assert info['streams'][0]['codec_name']=='mp3'
        duracao=float(info['format']['duration']);duracoes.append(duracao)
        assert abs(duracao-(caso['duracao_musical_s']+1))<.10
        volume=subprocess.run(['ffmpeg','-hide_banner','-i',str(mp3),'-af','volumedetect',
            '-f','null','-'],capture_output=True,text=True,check=True).stderr
        pico=re.search(r'max_volume:\s*([-\d.]+)\s*dB',volume)
        assert pico and float(pico.group(1))>-50,'Áudio vazio ou inaudível'
    assert abs(duracoes[0]-duracoes[1])<.03
    # exemplo de antes/depois precisa mostrar alguma diferença de nota
    assert notas_lado['antes']!=notas_lado['depois'],f"{caso['id']}: antes e depois têm as mesmas notas"
    print('[ok]',caso['id'],'notas/tempos, hashes, SVG/PDF e dois MP3 com mesma duração',flush=True)
alcance=next(c for c in manifesto['casos'] if c['id']=='04-alcance')
assert alcance['antes']['esquerda']['abertura_max_semitons']>12
assert alcance['depois']['esquerda']['abertura_max_semitons']<=12
intro=next(c for c in manifesto['casos'] if c['id']=='05-introducao')
assert intro['antes']['direita']['notas']==0 and intro['depois']['direita']['notas']>0
print(f'Conferidos {len(manifesto["casos"])} exemplos, 10 pares partitura/MIDI e {notas_total} notas.',flush=True)
