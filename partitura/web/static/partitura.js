// SVG e mapa de tempos são gerados juntos no servidor. Nenhum modelo no navegador.

// np.interp: interpolação linear, presa nas pontas. xs crescente.
function interpolar(x, xs, ys) {
  if (!xs.length) return x;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[xs.length-1]) return ys[ys.length-1];
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const mid = (lo+hi) >>> 1; if (xs[mid] <= x) lo = mid; else hi = mid; }
  return ys[lo] + (ys[hi]-ys[lo]) * (x-xs[lo]) / (xs[hi]-xs[lo]);
}
// Gravação original <-> segundos da partitura (os da prévia), pelas batidas detectadas.
// mapa: {bt, idx, desloc, bpm} de /api/partitura (cache/sincronia_original.json).
function originalParaPartitura(t, mapa) { return (interpolar(t, mapa.bt, mapa.idx) + mapa.desloc) * 60 / mapa.bpm; }
function partituraParaOriginal(s, mapa) { return interpolar(s * mapa.bpm / 60 - mapa.desloc, mapa.idx, mapa.bt); }

class LeitorPartitura {
  constructor({ area, audio, original, arquivo, mostrador, seguir, zoom, layout = 'pagina' }) {
    Object.assign(this, { area, audio, original, arquivo, mostrador, seguir, zoom, layout });
    this.fonte = audio;  // relógio atual: prévia ou gravação original
    this.abort = new AbortController();
    this.ativos = new Set();
    this.elementos = new Map();
    this.raf = null;
    this.indice = -2;
    this.sistema = null;
    this.suspenso = false;
    this.atualizar = this.atualizar.bind(this);
    // Só o relógio atual move a partitura; tocar o outro troca de relógio.
    this.reproduzir = (e) => {
      const el = e?.target || this.fonte;
      if (el === this.original && !this.mapaOriginal) { this.limpar(); return; }
      this.fonte = el;
      this.suspenso = false; this.sistema = null; this.indice = -2;
      cancelAnimationFrame(this.raf); this.atualizar();
    };
    this.pausar = (e) => { if (e && e.target !== this.fonte) return; cancelAnimationFrame(this.raf); this.raf = null; this.atualizar(false); };
    this.buscar = (e) => { if (e && e.target !== this.fonte) return; this.suspenso = false; this.sistema = null; this.indice = -2; this.atualizar(false); };
    this.redimensionar = () => { this.geometria = null; this.sistema = null; this.posicionarCursor(); };
    for (const el of [audio, original].filter(Boolean))
      for (const [tipo, fn] of [['play',this.reproduzir], ['pause',this.pausar], ['seeked',this.buscar], ['ended',this.pausar]])
        el.addEventListener(tipo, fn, { signal: this.abort.signal });
    window.addEventListener('resize', this.redimensionar, { signal: this.abort.signal });
    this.observador = new ResizeObserver(this.redimensionar);
    this.observador.observe(area);
    zoom.addEventListener('change', () => {
      area.querySelectorAll('.folha-partitura').forEach((p) => p.style.width = zoom.value + '%');
      this.redimensionar();
    }, { signal: this.abort.signal });
    seguir.addEventListener('change', () => { this.sistema = null; this.posicionarCursor(); }, { signal: this.abort.signal });
    area.addEventListener('click', (e) => {
      let el = e.target;
      while (el && el !== area) {
        if (this.inicios && Object.hasOwn(this.inicios, el.id)) {
          const s = this.inicios[el.id];
          if (this.fonte === this.original && this.mapaOriginal) this.original.currentTime = partituraParaOriginal(s, this.mapaOriginal);
          else this.audio.currentTime = s;
          this.buscar();
          return;
        }
        el = el.parentElement;
      }
    }, { signal: this.abort.signal });
    this.carregar();
  }

  async carregar() {
    try {
      const r = await fetch('/api/partitura?arquivo=' + encodeURIComponent(this.arquivo) + (this.layout !== 'pagina' ? '&layout=' + this.layout : ''), { signal: this.abort.signal, cache: 'no-store' });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Erro ao carregar a partitura.');
      if (this.abort.signal.aborted) return;
      this.quadros = d.quadros;
      this.inicios = d.inicios;
      this.percurso = d.percurso;
      this.mapaOriginal = d.original || null;
      this.area.innerHTML = d.paginas.map((svg, i) =>
        `<div class="folha-partitura" style="width:${this.zoom.value}%" aria-label="Página ${i+1}">${svg}<div class="cursor-partitura" hidden></div><span class="numero-folha">${i+1} / ${d.paginas.length}</span></div>`).join('');
      for (const el of this.area.querySelectorAll('[id]')) this.elementos.set(el.id, el);
      for (const id of Object.keys(this.inicios)) this.elementos.get(id)?.classList.add('nota-navegavel');
      this.atualizar();
    } catch (err) {
      if (err.name === 'AbortError') return;
      this.area.innerHTML = '<p>Não consegui abrir a partitura interativa. O PDF continua disponível abaixo.</p><button type="button" class="btn">Tentar novamente</button>';
      this.area.querySelector('button').addEventListener('click', () => {
        this.area.textContent = 'Carregando notas…';
        this.carregar();
      }, { once:true, signal:this.abort.signal });
      this.mostrador.textContent = err.message;
    }
  }

  // Segundos da partitura (= da prévia) no relógio atual.
  tempo() {
    if (this.fonte === this.original && this.mapaOriginal) return originalParaPartitura(this.original.currentTime, this.mapaOriginal);
    return this.audio.currentTime;
  }

  atualizar(agendar = true) {
    if (this.abort.signal.aborted || !this.quadros || this.suspenso) return;
    const t = this.tempo();
    let lo = 0, hi = this.quadros.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.quadros[mid].tempo <= t) lo = mid + 1;
      else hi = mid;
    }
    const indice = lo - 1;
    if (indice !== this.indice) {
      const novos = new Set(this.quadros[indice]?.notas || []);
      for (const id of this.ativos) if (!novos.has(id)) this.elementos.get(id)?.classList.remove('nota-tocando');
      for (const id of novos) this.elementos.get(id)?.classList.add('nota-tocando');
      this.ativos = novos;
      this.indice = indice;
    }
    // A barra segue o relógio do áudio a cada frame, mesmo sem ataques ou notas.
    this.posicionarCursor();
    const formatar = (s) => `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
    const relogio = this.fonte;
    const qual = relogio === this.original ? 'gravação original' : 'prévia de piano';
    const toque = matchMedia('(pointer: coarse)').matches ? 'toque' : 'clique';
    this.mostrador.textContent = `${formatar(relogio.currentTime)} / ${formatar(relogio.duration || this.quadros.at(-1)?.tempo || 0)} · ${qual} · ${toque} numa nota para ir até ela`;
    if (agendar && !relogio.paused && !relogio.ended) {
      cancelAnimationFrame(this.raf);
      this.raf = requestAnimationFrame(this.atualizar);
    }
  }

  medirPercurso() {
    this.geometria = [];
    for (const m of this.percurso || []) {
      const el = this.elementos.get(m.id);
      const pagina = el?.closest('.folha-partitura');
      if (!pagina || m.fim <= m.inicio) continue;
      const sistema = el.closest('.system') || el;
      // Limites pela pauta e pela barra de compasso, não pela caixa do compasso inteiro: ligadura de nota
      // longa, linha de 8va ou dedo ao lado esticam a caixa até o fim da linha, e o cursor corria até lá e
      // voltava quando o compasso seguinte começava.
      const pauta = el.querySelector(':scope > .staff') || el, barra = el.querySelector(':scope > .barLine');
      const p = pagina.getBoundingClientRect(), r = pauta.getBoundingClientRect(), s = sistema.getBoundingClientRect();
      let esquerda = r.left - p.left + 8;
      const direita = (barra ? barra.getBoundingClientRect().left : r.right) - p.left - 4;
      for (const cabecalho of el.querySelectorAll('.clef,.keySig,.meterSig'))
        esquerda = Math.max(esquerda, cabecalho.getBoundingClientRect().right - p.left + 10);
      const porTempo = new Map();
      for (const ponto of m.pontos) {
        if (ponto.pausa_compasso) continue; // pausa de compasso é centralizada, não é o início do tempo
        const simbolo = this.elementos.get(ponto.id);
        if (!simbolo || simbolo.closest('.folha-partitura') !== pagina) continue;
        const alvo = simbolo.querySelector('.notehead') || simbolo;
        const x = alvo.getBoundingClientRect().left - p.left;
        porTempo.set(ponto.tempo, Math.min(x, porTempo.get(ponto.tempo) ?? Infinity));
      }
      const pontos = [...porTempo].filter(([t]) => t >= m.inicio && t < m.fim)
        .sort((a,b) => a[0]-b[0]);
      if (!pontos.length || pontos[0][0] > m.inicio) pontos.unshift([m.inicio, esquerda]);
      pontos.push([m.fim, Math.max(esquerda, direita)]);
      // Cabeças de acordes/vozes podem estar deslocadas; o tempo nunca anda para trás.
      let xAnterior = esquerda;
      for (const ponto of pontos) ponto[1] = xAnterior = Math.max(xAnterior, Math.min(direita, ponto[1]));
      this.geometria.push({ ...m, pagina, sistema, pontos, y:s.top-p.top, altura:s.height });
    }
    // Trava: na mesma linha, o fim de um compasso nunca passa do começo do seguinte.
    for (let i = 0; i + 1 < this.geometria.length; i++) {
      const a = this.geometria[i], b = this.geometria[i + 1];
      if (a.sistema !== b.sistema) continue;
      const limite = b.pontos[0][1];
      for (const ponto of a.pontos) ponto[1] = Math.min(ponto[1], limite);
    }
  }

  posicionarCursor() {
    if (this.suspenso || !this.percurso) return;
    if (!this.geometria) this.medirPercurso();
    if (!this.geometria.length) return;
    const t = this.tempo();
    let lo = 0, hi = this.geometria.length;
    while (lo < hi) {
      const mid = (lo+hi) >>> 1;
      if (this.geometria[mid].inicio <= t) lo = mid+1;
      else hi = mid;
    }
    const m = this.geometria[Math.max(0,lo-1)];
    const tempo = Math.max(m.inicio,Math.min(m.fim,t));
    let i = 0;
    while (i+1 < m.pontos.length-1 && m.pontos[i+1][0] <= tempo) i++;
    const [ta,xa] = m.pontos[i], [tb,xb] = m.pontos[i+1];
    const x = xa + (xb-xa) * (tb>ta ? (tempo-ta)/(tb-ta) : 0);
    const cursor = m.pagina.querySelector('.cursor-partitura');
    if (this.cursorAtual !== cursor) {
      if (this.cursorAtual) this.cursorAtual.hidden = true;
      this.cursorAtual = cursor;
    }
    cursor.hidden = false;
    cursor.style.left = x + 'px';
    cursor.style.top = Math.max(0,m.y) + 'px';
    cursor.style.height = Math.max(20,m.altura) + 'px';
    if (this.seguir.checked) {
      const a = this.area.getBoundingClientRect(), p = m.pagina.getBoundingClientRect();
      const top = p.top+m.y, bottom = top+m.altura, cx = p.left+x;
      const fora = top < a.top+12 || (bottom>a.bottom-12 && m.altura<a.height-24) || cx<a.left+12 || cx>a.right-12;
      if (fora && (this.sistema !== m.sistema || performance.now()-(this.ultimoScroll || 0)>600)) {
        this.area.scrollTo({top:Math.max(0,this.area.scrollTop+top-a.top-30),
          left:Math.max(0,this.area.scrollLeft+cx-a.left-80),behavior:'smooth'});
        this.ultimoScroll = performance.now();
      }
    }
    this.sistema = m.sistema;
  }

  limpar() {
    this.suspenso = true;
    for (const id of this.ativos) this.elementos.get(id)?.classList.remove('nota-tocando');
    this.ativos.clear();
    this.indice = -2;
    this.area.querySelectorAll('.cursor-partitura').forEach((c) => c.hidden = true);
    this.mostrador.textContent = 'O destaque acompanha a prévia de piano.';
  }

  destruir() {
    cancelAnimationFrame(this.raf);
    this.abort.abort();
    this.observador.disconnect();
  }
}
window.LeitorPartitura = LeitorPartitura;
if (typeof module !== 'undefined') module.exports = { interpolar, originalParaPartitura, partituraParaOriginal };
