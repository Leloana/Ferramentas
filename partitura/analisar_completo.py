"""Auditoria local das partituras existentes, sem GPU, rede ou regeneração.

Executar: venv/Scripts/python.exe analisar_completo.py
Mede eventos ligados como uma nota e também notas sustentadas simultâneas.
As referências de harmonia e melodia são estimativas do próprio pipeline.
"""
from pathlib import Path
import json
import sys
from collections import defaultdict, Counter
import numpy as np
from music21 import converter, harmony, tempo, key
from sincronia import preparar_musicxml,notas_ligadas

RAIZ = Path(__file__).resolve().parent


def ler(caminho):
    sc = converter.parse(str(caminho))
    marcas = list(sc.flatten().getElementsByClass(tempo.MetronomeMark))
    bpm = float(marcas[0].getQuarterBPM()) if marcas else 100.0
    _,segmentos=preparar_musicxml(caminho.read_text(encoding='utf-8'))
    ns=notas_ligadas(segmentos)
    varias_partes=any(int(n['voz'].split(':')[0])>0 for n in ns)
    maos=[[],[]]
    for n in ns:
        voz=n['voz'].split(':')
        mao=int(voz[0]) if varias_partes else int(voz[1])-1
        if mao<2:
            maos[mao].append((n['inicio']*bpm/60,(n['fim']-n['inicio'])*bpm/60,[n['pitch']],n['letra']))
    maos=[sorted(m,key=lambda e:e[0]) for m in maos]
    plana = sc.parts[0].flatten()
    cifras = [(float(c.offset), {p.pitchClass for p in c.pitches})
              for c in plana.getElementsByClass(harmony.ChordSymbol)]
    arm = [(float(k.offset), k.sharps) for k in plana.getElementsByClass(key.KeySignature)]
    return maos, bpm, cifras, arm


def mao(ev, bpm, fim):
    dur_s = max(fim * 60 / bpm, 1)
    ataques = sorted({o for o, d, ps, ly in ev})
    aberturas, polifonias = [], []
    for o in ataques:
        ps = {p for a, d, ns, _ in ev if a <= o + 1e-7 and a + d > o + 1e-7 for p in ns}
        aberturas.append(max(ps) - min(ps) if ps else 0)
        polifonias.append(len(ps))
    acordes = [a for a, p in zip(aberturas, polifonias) if p > 1]
    baixos=[min(p for a,d,ps,ly in ev if abs(a-o)<1e-7 for p in ps) for o in ataques]
    saltos = [abs(b-a) for a,b in zip(baixos,baixos[1:])]
    segundos = [o * 60 / bpm for o in ataques]
    pico = max((sum(t <= u < t + 10 for u in segundos) / 10 for t in segundos), default=0)
    return dict(notas_s=sum(len(ps) for _, _, ps, _ in ev) / dur_s,
                ataques_s=len(ataques) / dur_s, pico_ataques_s_10s=pico,
                abertura_maior_oitava_pct=100 * np.mean([a > 12 for a in acordes]) if acordes else 0,
                abertura_max=max(aberturas, default=0),
                polifonia_max=max(polifonias, default=0),
                salto_p95=float(np.percentile(saltos, 95)) if saltos else 0,
                saltos_maior_oitava_pct=100 * np.mean([s > 12 for s in saltos]) if saltos else 0,
                notas_curtas_pct=100 * np.mean([d * 60 / bpm < .15 for _, d, _, _ in ev]) if ev else 0)


def similaridade(md, ref):
    # Interseção temporal da nota superior, em classes de altura. Referência
    # monofônica do Acordes: mede concordância, não acurácia contra a gravação.
    total = bate = 0.0
    for a, d, ps, _ in ref:
        bordas = sorted({a, a+d} | {max(a, min(a+d, t)) for o, du, _, _ in md for t in (o, o+du)})
        for x, y in zip(bordas, bordas[1:]):
            t = (x+y)/2
            ativos = [p for o, du, ns, _ in md if o <= t < o+du for p in ns]
            total += y-x
            if ativos and max(ativos) % 12 == max(ps) % 12:
                bate += y-x
    return 100 * bate / total if total else None


def deslocamento(cifras, referencia):
    """Os exports começam em compassos diferentes conforme o primeiro baixo.
    Recupera a origem comum pelo deslocamento que alinha mais cifras iguais.
    """
    votos = Counter(round(b-a, 6) for a, pcs in cifras for b, ref in referencia if pcs == ref)
    return max(votos, key=lambda v: (votos[v], -abs(v))) if votos else 0.0


def main():
    linhas = []
    antes='--antes' in sys.argv
    origem=RAIZ/'trabalho/revisao_20261109' if antes else RAIZ/'saida'
    for pasta in sorted(origem.iterdir()):
        arquivos = sorted((pasta / 'editaveis').glob('*.musicxml')) if pasta.is_dir() else []
        dados = {}
        for arq in arquivos:
            try:
                versao, nivel = arq.stem.split(' - ')
            except ValueError:
                continue
            dados[(versao, nivel)] = (arq, ler(arq))
        for (versao, nivel), (arq, (maos, bpm, cifras, arm)) in dados.items():
            fim = max((o+d for ev in maos for o, d, _, _ in ev), default=0)
            ref = dados.get(('Acordes', nivel))
            md, me = (maos + [[], []])[:2]
            delta = deslocamento(cifras, ref[1][2]) if ref else 0
            md_alinhada = [(o+delta, d, ps, ly) for o,d,ps,ly in md]
            harm_total = harm_bate = 0
            for ev in maos:
                for o, d, ps, _ in ev:
                    vigente = [pcs for a, pcs in cifras if a <= o+1e-7]
                    if vigente:
                        harm_total += d*len(ps)
                        harm_bate += d*sum(p % 12 in vigente[-1] for p in ps)
            linha = dict(musica=pasta.name, versao=versao, nivel=nivel,
                         arquivo=str(arq.relative_to(RAIZ)), bpm=bpm, duracao_s=fim*60/bpm,
                         direita=mao(md, bpm, fim), esquerda=mao(me, bpm, fim),
                         mudancas_armadura=sum(a[1] != b[1] for a,b in zip(arm,arm[1:])),
                         ataques_com_letra=sum(ly for _, _, _, ly in md),
                         harmonia_estimada_pct=100*harm_bate/harm_total if harm_total else None,
                         alinhamento_tempos=delta,
                         concordancia_melodia_pct=similaridade(md_alinhada, ref[1][0][0]) if ref else None)
            linhas.append(linha)
        if dados:
            print(f'{pasta.name}: {len(dados)} partituras', flush=True)
    destino=origem/('analise_antes.json' if antes else 'analise_completa.json')
    destino.write_text(json.dumps(linhas, ensure_ascii=False, indent=2), encoding='utf-8')
    grupos = defaultdict(list)
    for l in linhas:
        grupos[(l['nivel'], l['versao'])].append(l)
    resumo = []
    for (nivel, versao), ls in sorted(grupos.items()):
        r = dict(nivel=nivel, versao=versao, musicas=len(ls))
        for hand in ('direita','esquerda'):
            for k in ls[0][hand]:
                r[hand+'_'+k] = float(np.mean([l[hand][k] for l in ls]))
        for k in ('mudancas_armadura','ataques_com_letra','harmonia_estimada_pct','concordancia_melodia_pct'):
            xs=[l[k] for l in ls if l[k] is not None]
            r[k]=float(np.mean(xs)) if xs else None
        resumo.append(r)
    destino=origem/('resumo_antes.json' if antes else 'analise_resumo.json')
    destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'TOTAL: {len(linhas)} partituras; {len({l["musica"] for l in linhas})} músicas', flush=True)
    for r in resumo:
        print(r['nivel'], r['versao'], 'n=',r['musicas'], 'notas/s D/E', round(r['direita_notas_s'],2), round(r['esquerda_notas_s'],2), 'aberturas D/E', round(r['direita_abertura_maior_oitava_pct'],1), round(r['esquerda_abertura_maior_oitava_pct'],1), 'saltos E', round(r['esquerda_salto_p95'],1), 'harm', round(r['harmonia_estimada_pct'] or 0,1), 'mel',round(r['concordancia_melodia_pct'] or 0,1), flush=True)


if __name__ == '__main__':
    main()
