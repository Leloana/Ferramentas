"""Página de comparação às cegas entre duas bibliotecas (antes/depois de uma mudança).

Pra cada música e versão/nível presente nos dois lados, acha o trecho de 4 compassos que
mais mudou (alinhando os dois lados pela melodia cantada, porque a introdução gerada
desloca os compassos), recorta os dois MusicXML, desenha (dedos sem números, pra não
denunciar o lado) e toca com o mesmo piano das prévias. Opções embaralhadas, nota de 1 a 5,
"melhor", revelar com a partitura de cada lado, resultado copiável.
"""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path


import gerar
from metricas import notas_do_xml

PADRAO = {"Facil": "Acordes", "Medio": "HibridoAMT", "Dificil": "HibridoAMT"}


def _bpm(xml: Path) -> float:
    import re
    m = re.search(r'<sound[^>]*tempo="([\d.]+)"', xml.read_text(encoding="utf-8"))
    return float(m.group(1)) if m else 120.0


def _por_compasso(notas, bpm):
    """{compasso: {(tempo no compasso, altura)}} das duas mãos (4/4)."""
    saida = {}
    for n in notas:
        q = n["inicio"] * bpm / 60
        saida.setdefault(int(q // 4), set()).add((round(q % 4, 2), n["pitch"]))
    return saida


def alinhar(antes, depois, bpm_a, bpm_d, max_desloc=24):
    """Deslocamento em compassos (depois = antes + k) que mais casa a melodia cantada."""
    def mel(ns, bpm):
        return {(int(n["inicio"] * bpm / 60 // 4), round(n["inicio"] * bpm / 60 % 4, 2), n["pitch"])
                for n in ns if n["mao"] == "direita" and n["letra"]}
    ma, md = mel(antes, bpm_a), mel(depois, bpm_d)
    melhor = max(range(-max_desloc, max_desloc + 1),
                 key=lambda k: (len({(c + k, t, p) for c, t, p in ma} & md), -abs(k)))
    return melhor


def trecho_que_mais_mudou(antes, depois, bpm_a, bpm_d, k, tamanho=4, evitar=()):
    ca, cd = _por_compasso(antes, bpm_a), _por_compasso(depois, bpm_d)
    if not cd:
        return None, 0
    dif = {c: len(cd.get(c, set()) ^ ca.get(c - k, set())) for c in range(min(cd), max(cd) + 1)}
    melhor, valor = None, 0
    for c0 in range(min(cd), max(cd) - tamanho + 2):
        if any(c in evitar for c in range(c0, c0 + tamanho)):
            continue
        v = sum(dif.get(c, 0) for c in range(c0, c0 + tamanho))
        if v > valor:
            melhor, valor = c0, v
    return melhor, valor


def recortar(xml: Path, c_ini: int, c_fim: int, destino: Path):
    """Compassos [c_ini, c_fim] (contados de 0 a partir do 1º compasso do arquivo)."""
    from music21 import converter
    sc = converter.parse(str(xml))
    numeros = [m.number for m in sc.parts[0].getElementsByClass("Measure")]
    a, b = numeros[max(0, c_ini)], numeros[min(len(numeros) - 1, c_fim)]
    trecho = sc.measures(a, b)
    trecho.write("musicxml", fp=str(destino))
    return destino


def desenhar(xml: Path, destino: Path, sem_dedos=False):
    import re
    import verovio
    tk = verovio.toolkit()
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    tk.setOptions({"pageWidth": 2100, "pageHeight": 3000, "scale": 40, "adjustPageHeight": True,
                   "footer": "none", "header": "none", "breaks": "auto", **gerar.OPCOES_DEDOS})
    texto = xml.read_text(encoding="utf-8")
    if sem_dedos:
        texto = re.sub(r"<fingering[^>]*>\d+</fingering>", "", texto)
    tk.loadData(gerar.xml_para_verovio(texto))
    svg = gerar.pedal_continuo(gerar.dedos_ao_lado(gerar._desembaralhar(tk.renderToSVG(1))))
    destino.write_text(svg.replace("<svg ", '<svg style="background:#fff" ', 1), encoding="utf-8")


def tocar(xml: Path, destino: Path):
    from music21 import converter
    mid = destino.with_suffix(".mid")
    gerar.salvar_midi_notas(converter.parse(str(xml)), mid, xml)
    gerar.midi_para_mp3(mid, destino)


def montar_pagina(antes_dir: Path, depois_dir: Path, saida: Path, niveis=("Facil", "Medio", "Dificil"),
                  rotulos=("antes", "depois"), semente=7319):
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    rnd = random.Random(semente)
    casos, sem_mudanca = [], []
    for pasta_d in sorted(p for p in depois_dir.iterdir() if p.is_dir()):
        pasta_a = antes_dir / pasta_d.name
        if not pasta_a.exists():
            continue
        for nivel in niveis:
            vn = f"{PADRAO[nivel]} - {nivel}"
            xa, xd = pasta_a / "editaveis" / f"{vn}.musicxml", pasta_d / "editaveis" / f"{vn}.musicxml"
            if not (xa.exists() and xd.exists()):
                vn = f"Acordes - {nivel}"
                xa, xd = pasta_a / "editaveis" / f"{vn}.musicxml", pasta_d / "editaveis" / f"{vn}.musicxml"
                if not (xa.exists() and xd.exists()):
                    continue
            na, nd = notas_do_xml(xa), notas_do_xml(xd)
            ba, bd = _bpm(xa), _bpm(xd)
            k = alinhar(na, nd, ba, bd)
            evitar = set()
            for nome in ("introducao", "final"):   # trecho gerado não tem par no antes
                arq = pasta_d / "cache" / f"{nome}_{nivel.lower()}.json"
                if arq.exists():
                    n_c = json.loads(arq.read_text(encoding="utf-8"))["compassos"]
                    todos = sorted(_por_compasso(nd, bd))
                    evitar |= set(todos[:n_c]) if nome == "introducao" else set(todos[-n_c:])
            c0, valor = trecho_que_mais_mudou(na, nd, ba, bd, k, evitar=evitar)
            if c0 is None or valor == 0:
                sem_mudanca.append(f"{pasta_d.name} · {vn}")
                continue
            ident = f"{pasta_d.name} · {vn}"
            pasta = saida / f"{len(casos):02d}"
            pasta.mkdir()
            primeiro_d = min(_por_compasso(nd, bd))
            primeiro_a = min(_por_compasso(na, ba))
            opcoes = []
            for rot, xml, ini in ((rotulos[0], xa, c0 - k - primeiro_a), (rotulos[1], xd, c0 - primeiro_d)):
                cut = recortar(xml, ini, ini + 3, pasta / f"{rot}.musicxml")
                desenhar(cut, pasta / f"{rot}.svg")
                desenhar(cut, pasta / f"{rot}_cego.svg", sem_dedos=True)
                tocar(cut, pasta / f"{rot}.mp3")
                opcoes.append(dict(id=rot, rotulo=rot, mp3=f"{pasta.name}/{rot}.mp3", svg=f"{pasta.name}/{rot}.svg",
                                   cego=f"{pasta.name}/{rot}_cego.svg", medidas={}, correcoes=[]))
            rnd.shuffle(opcoes)
            for letra, o in zip("AB", opcoes):
                o["letra"] = letra
            casos.append(dict(id=ident, titulo=ident, musica=pasta_d.name, versao=vn,
                              ouvir="Trecho de 4 compassos onde as duas versões mais diferem.",
                              opcoes=opcoes, diferem=[1, 2, 3, 4], pares=[dict(a="A", b="B", compassos=[1, 2, 3, 4])],
                              so_dedos=None))
            print("[pagina]", ident, "compassos", c0 + 1, "a", c0 + 4, "diferenças", valor, flush=True)
    dados = dict(casos=casos, descartados=[dict(id=s, titulo=s) for s in sem_mudanca])
    (saida / "casos.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    (saida / "index.html").write_text(MODELO.replace("__CASOS__", json.dumps(dados, ensure_ascii=False)),
                                      encoding="utf-8")
    return saida / "index.html"


def montar_pagina_varias(lados: dict, saida: Path, casos: list, semente=7319, ouvir=None):
    """Página às cegas com várias opções por trecho (ex.: padrão × 5 teores de acompanhamento).

    lados: {rótulo: biblioteca}; o 1º é a referência do alinhamento. casos: [(música, "Versao - Nivel")].
    O trecho é o de 4 compassos que mais muda somando todas as opções contra a referência.
    """
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    rnd = random.Random(semente)
    rotulos = list(lados)
    saida_casos, sem = [], []
    for musica, vn in casos:
        xmls = {r: Path(lados[r]) / musica / "editaveis" / f"{vn}.musicxml" for r in rotulos}
        if not all(x.exists() for x in xmls.values()):
            sem.append(f"{musica} · {vn} (falta arquivo)")
            continue
        notas = {r: notas_do_xml(x) for r, x in xmls.items()}
        bpms = {r: _bpm(x) for r, x in xmls.items()}
        ref = rotulos[0]
        cref = _por_compasso(notas[ref], bpms[ref])
        ks = {r: alinhar(notas[ref], notas[r], bpms[ref], bpms[r]) for r in rotulos}
        soma = {}
        for r in rotulos[1:]:
            co = _por_compasso(notas[r], bpms[r])
            for c in cref:
                soma[c] = soma.get(c, 0) + len(cref[c] ^ co.get(c + ks[r], set()))
        janelas = [(sum(soma.get(c, 0) for c in range(c0, c0 + 4)), c0) for c0 in sorted(cref)[:-3] or sorted(cref)]
        valor, c0 = max(janelas) if janelas else (0, None)
        if not valor:
            sem.append(f"{musica} · {vn}")
            continue
        pasta = saida / f"{len(saida_casos):02d}"
        pasta.mkdir()
        opcoes = []
        for i, r in enumerate(rotulos):
            ini = c0 + ks[r] - min(_por_compasso(notas[r], bpms[r]))
            nome = f"op{i}"
            cut = recortar(xmls[r], ini, ini + 3, pasta / f"{nome}.musicxml")
            desenhar(cut, pasta / f"{nome}.svg")
            desenhar(cut, pasta / f"{nome}_cego.svg", sem_dedos=True)
            tocar(cut, pasta / f"{nome}.mp3")
            opcoes.append(dict(id=r, rotulo=r, mp3=f"{pasta.name}/{nome}.mp3", svg=f"{pasta.name}/{nome}.svg",
                               cego=f"{pasta.name}/{nome}_cego.svg", medidas={}, correcoes=[]))
        rnd.shuffle(opcoes)
        for letra, o in zip("ABCDEFGHIJ", opcoes):
            o["letra"] = letra
        ident = f"{musica} · {vn}"
        saida_casos.append(dict(id=ident, titulo=ident, musica=musica, versao=vn,
                                ouvir=ouvir or "Trecho de 4 compassos onde as opções mais diferem.",
                                opcoes=opcoes, diferem=[1, 2, 3, 4], pares=[], so_dedos=None))
        print("[pagina]", ident, "compassos", c0 + 1, "a", c0 + 4, "diferenças", valor, flush=True)
    dados = dict(casos=saida_casos, descartados=[dict(id=x, titulo=x) for x in sem])
    (saida / "casos.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    (saida / "index.html").write_text(MODELO.replace("__CASOS__", json.dumps(dados, ensure_ascii=False)),
                                      encoding="utf-8")
    return saida / "index.html"


MODELO = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparar partituras</title>
<style>
:root{--bg:#f6f3ee;--card:#fff;--tx:#1f1b16;--mut:#6b6258;--li:#e3ddd3;--ac:#b5651d}
@media (prefers-color-scheme:dark){:root{--bg:#171512;--card:#221f1b;--tx:#efe9e1;--mut:#a39a8f;--li:#3a352f;--ac:#e09a52}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mut)}
section{background:var(--card);border:1px solid var(--li);border-radius:10px;padding:20px;margin:0 0 20px}
h2{font-size:20px;margin:0}.op{border:1px solid var(--li);border-radius:8px;padding:12px;margin-top:12px}
.op.melhor{box-shadow:0 0 0 2px var(--ac) inset}.topo{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.topo audio{flex:1;min-width:220px}.letra{font-size:22px;font-weight:700}
button{font:inherit;cursor:pointer;border:1px solid var(--li);background:transparent;color:var(--tx);border-radius:6px;padding:6px 12px}
button.on,button.principal{background:var(--ac);border-color:var(--ac);color:#fff}
.folha{background:#fff;border-radius:6px;padding:6px;margin-top:10px;overflow-x:auto}.folha img{display:block;width:100%;min-width:640px}
.rev{display:none;margin-top:16px}section.revelado .rev{display:block}.rotulo{color:var(--ac);font-weight:600}
textarea{width:100%;min-height:50px;font:inherit;color:var(--tx);background:transparent;border:1px solid var(--li);border-radius:6px;padding:8px;margin-top:12px}
.fim{position:sticky;bottom:0;background:var(--bg);border-top:1px solid var(--li);padding:12px;display:flex;gap:10px;justify-content:center}
</style></head><body><main><h1>Comparar partituras</h1>
<p class="sub">Ouça e leia às cegas, dê nota de 1 a 5 e marque a melhor. Depois revele.</p>
<div id="casos"></div><p class="sub" id="fora"></p></main>
<div class="fim"><button class="principal" id="copiar">Copiar resultado</button><span id="aviso"></span></div>
<script>
const VER = Date.now();
const DADOS = __CASOS__;
const CHAVE = 'comparacao-cega-' + location.pathname;
let estado = {}; try { estado = JSON.parse(localStorage.getItem(CHAVE) || '{}'); } catch (e) {}
const salvar = () => { try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch (e) {} };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function desenhar() {
  const raiz = document.getElementById('casos'); raiz.innerHTML = '';
  for (const c of DADOS.casos) {
    const e = estado[c.id] ||= {notas:{}, melhor:null, comentario:'', revelado:false};
    const s = document.createElement('section'); if (e.revelado) s.classList.add('revelado');
    s.innerHTML = `<h2>${esc(c.titulo)}</h2><p class="sub">${esc(c.ouvir)}</p>` + c.opcoes.map((o) => `
      <div class="op ${e.melhor === o.letra ? 'melhor' : ''}" data-l="${o.letra}"><div class="topo"><div class="letra">${o.letra}</div>
      <audio controls preload="none" src="${o.mp3}?v=${VER}"></audio>
      ${[1,2,3,4,5].map((n) => `<button data-n="${n}" class="${e.notas[o.letra] === n ? 'on' : ''}">${n}</button>`).join('')}
      <button class="m ${e.melhor === o.letra ? 'on' : ''}">melhor</button></div>
      <div class="folha"><img src="${o.cego}?v=${VER}" alt=""></div></div>`).join('') + `
      <textarea placeholder="comentário (opcional)">${esc(e.comentario)}</textarea>
      <p><button class="principal rv">${e.revelado ? 'Esconder' : 'Revelar'}</button></p>
      <div class="rev">${c.opcoes.map((o) => `<h3>${o.letra}: <span class="rotulo">${esc(o.rotulo)}</span></h3>
      <div class="folha"><img loading="lazy" src="${o.svg}?v=${VER}" alt=""></div>`).join('')}</div>`;
    s.querySelectorAll('.op').forEach((op) => {
      const L = op.dataset.l;
      op.querySelectorAll('[data-n]').forEach((b) => b.onclick = () => { e.notas[L] = +b.dataset.n; salvar(); desenhar(); });
      op.querySelector('.m').onclick = () => { e.melhor = e.melhor === L ? null : L; salvar(); desenhar(); };
    });
    s.querySelector('textarea').oninput = (ev) => { e.comentario = ev.target.value; salvar(); };
    s.querySelector('.rv').onclick = () => { e.revelado = !e.revelado; salvar(); desenhar(); };
    s.querySelectorAll('audio').forEach((a) => a.addEventListener('play', () =>
      document.querySelectorAll('audio').forEach((b) => { if (b !== a) b.pause(); })));
    raiz.appendChild(s);
  }
}
document.getElementById('copiar').onclick = async () => {
  const txt = DADOS.casos.map((c) => { const e = estado[c.id] || {}; const nome = (L) => (c.opcoes.find((o) => o.letra === L) || {}).id || '-';
    return `${c.id}: ${c.opcoes.map((o) => `${o.id}=${(e.notas||{})[o.letra] ?? '-'}`).join(' ')}; melhor ${nome(e.melhor)}${e.comentario ? '; "' + e.comentario + '"' : ''}`; }).join('\n');
  try { await navigator.clipboard.writeText(txt); document.getElementById('aviso').textContent = 'Copiado.'; } catch (e) { prompt('Copie:', txt); }
};
desenhar();
if (DADOS.descartados.length) document.getElementById('fora').textContent = 'Sem diferença: ' + DADOS.descartados.map((d) => d.titulo).join(', ');
</script></body></html>"""
