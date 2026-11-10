"""Partitura SVG com o mapa de reprodução do mesmo MusicXML."""
import json
import threading
import xml.etree.ElementTree as ET
from sincronia import preparar_musicxml
from pathlib import Path
from gerar import OPCOES_DEDOS, _desembaralhar, dedos_ao_lado, pedal_continuo

_TRAVA = threading.Lock()
VERSAO = 11
# Desenho da página. "pagina" = A4 (tela grande e PDF); "retrato"/"paisagem" = modo foco no
# celular: página estreita e contínua (uma folha comprida), poucos compassos por linha, para
# a pauta ficar grande na tela pequena.
LAYOUTS = {
    'pagina': {'pageWidth': 2100, 'pageHeight': 2970, 'adjustPageHeight': False,
               'pageMarginLeft': 80, 'pageMarginRight': 80},
    'retrato': {'pageWidth': 850, 'pageHeight': 60000, 'adjustPageHeight': True,
                'pageMarginLeft': 30, 'pageMarginRight': 30},
    'paisagem': {'pageWidth': 2200, 'pageHeight': 60000, 'adjustPageHeight': True,
                 'pageMarginLeft': 40, 'pageMarginRight': 40},
}


def mapa_original(sinc: Path, versao: str, texto: str):
    """Batidas da gravação + deslocamento desta versão + andamento da partitura, ou None.

    No navegador: segundos da partitura s -> posição q = s*bpm/60 -> original
    t = interp(q - desloc, idx, bt). Gerações antigas não têm o arquivo: só a prévia."""
    if not sinc.exists():
        return None
    try:
        dados=json.loads(sinc.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return None
    if versao not in dados.get('versoes',{}) or len(dados.get('bt',[]))<2:
        return None
    som=ET.fromstring(texto).find('.//sound[@tempo]')
    bpm=float(som.get('tempo')) if som is not None else 120.0
    return {'bt':dados['bt'],'idx':dados['idx'],'desloc':dados['versoes'][versao],'bpm':bpm}


def renderizar(xml: Path, layout: str = 'pagina'):
    # Verovio usa estado global nativo; serializar renderizações dentro do servidor.
    if layout not in LAYOUTS:
        raise ValueError('Layout desconhecido.')
    with _TRAVA:
        stat=xml.stat()
        sinc=xml.parent.parent/'cache'/'sincronia_original.json'
        sinc_mtime=sinc.stat().st_mtime_ns if sinc.exists() else 0
        chave=f'{VERSAO}:{stat.st_mtime_ns}:{stat.st_size}:{sinc_mtime}'+('' if layout=='pagina' else f":{layout}:{LAYOUTS[layout]['pageWidth']}")
        sufixo='' if layout=='pagina' else f'.{layout}'
        cache=xml.parent.parent/'cache'/f'visor_{xml.stem}{sufixo}.json'
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
        tk.setOptions({'scale':42,'pageMarginTop':80,'pageMarginBottom':80,
                       'footer':'none','breaks':'auto',**LAYOUTS[layout],**OPCOES_DEDOS})
        texto,segmentos,percurso=preparar_musicxml(xml.read_text(encoding='utf-8'),com_percurso=True)
        if not tk.loadData(texto):
            raise ValueError('Não foi possível abrir esta partitura.')
        paginas=[pedal_continuo(dedos_ao_lado(_desembaralhar(tk.renderToSVG(i)))) for i in range(1,tk.getPageCount()+1)]
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
                   'duracao':percurso[-1]['fim'] if percurso else 0,
                   'original':mapa_original(sinc,xml.stem,texto)}
        cache.parent.mkdir(parents=True,exist_ok=True)
        # Troca atômica para não oferecer cache incompleto.
        temporario=cache.with_suffix('.json.tmp')
        temporario.write_text(json.dumps(resultado,ensure_ascii=False),encoding='utf-8')
        temporario.replace(cache)
        return resultado
