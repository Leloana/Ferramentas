"""Partitura SVG com o mapa de reprodução do mesmo MusicXML."""
import json
import threading
import xml.etree.ElementTree as ET
from sincronia import preparar_musicxml
from pathlib import Path
from gerar import _desembaralhar

_TRAVA = threading.Lock()
VERSAO = 7


def renderizar(xml: Path):
    # Verovio usa estado global nativo; serializar renderizações dentro do servidor.
    with _TRAVA:
        stat=xml.stat()
        chave=f'{VERSAO}:{stat.st_mtime_ns}:{stat.st_size}'
        cache=xml.parent.parent/'cache'/f'visor_{xml.stem}.json'
        if cache.exists():
            try:
                salvo=json.loads(cache.read_text(encoding='utf-8'))
                if salvo.get('chave')==chave:
                    return salvo
            except (OSError,ValueError):
                pass
        import verovio
        verovio.enableLog(False)
        tk=verovio.toolkit()
        tk.setResourcePath(str(Path(verovio.__file__).parent/'data'))
        tk.setOptions({'pageWidth':2100,'pageHeight':2970,'scale':42,
                       'pageMarginTop':80,'pageMarginBottom':80,
                       'pageMarginLeft':80,'pageMarginRight':80,
                       'adjustPageHeight':False,'footer':'none','breaks':'auto'})
        texto,segmentos,percurso=preparar_musicxml(xml.read_text(encoding='utf-8'),com_percurso=True)
        if not tk.loadData(texto):
            raise ValueError('Não foi possível abrir esta partitura.')
        paginas=[_desembaralhar(tk.renderToSVG(i)) for i in range(1,tk.getPageCount()+1)]
        # O relógio vem do MusicXML/MIDI, nunca da interpretação rítmica do
        # importador gráfico. O SVG preserva os IDs que atribuímos acima.
        agrupados={}
        ids={e.get('id') for svg in paginas for e in ET.fromstring(svg).iter() if e.get('id')}
        for s in segmentos:
            if s['id'] not in ids:
                raise ValueError('Uma nota não foi desenhada; tente abrir o PDF.')
            agrupados.setdefault(s['inicio'],{'on':[],'off':[]})['on'].append(s['id'])
            agrupados.setdefault(s['fim'],{'on':[],'off':[]})['off'].append(s['id'])
        ativos=set()
        quadros=[]
        inicios={}
        for t,eventos in sorted(agrupados.items()):
            ativos.difference_update(eventos['off'])
            ativos.update(eventos['on'])
            for ident in eventos['on']:
                inicios.setdefault(ident,t)
            quadros.append({'tempo':t,'notas':sorted(ativos)})
        resultado={'chave':chave,'paginas':paginas,'quadros':quadros,
                   'inicios':inicios,'percurso':percurso,
                   'duracao':percurso[-1]['fim'] if percurso else 0}
        cache.parent.mkdir(parents=True,exist_ok=True)
        # Troca atômica para não oferecer cache incompleto.
        temporario=cache.with_suffix('.json.tmp')
        temporario.write_text(json.dumps(resultado,ensure_ascii=False),encoding='utf-8')
        temporario.replace(cache)
        return resultado
