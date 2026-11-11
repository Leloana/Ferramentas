// Partitura — buscar → gerar (AMT-APC, modo leve) → tocar e ler no nível escolhido. Vanilla JS.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const semAcento = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const icone = (nome) => `<svg class="ic" aria-hidden="true"><use href="icones/sprite.svg#i-${nome}"/></svg>`;
const fmt = (s) => (isFinite(s) && s > 0 ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");
const capa = (id) => (id ? `https://i.ytimg.com/vi/${id}/mqdefault.jpg` : "");
const NIVEIS = { facil: "Fácil", medio: "Médio", dificil: "Difícil" };
const NIVEL_ARQ = { facil: "Facil", medio: "Medio", dificil: "Dificil" };
// uma versão só no site; música antiga sem AMT-APC usa a primeira que tiver
const VERSOES = ["AMT-APC", "HibridoAMT", "Hibrido", "Acordes", "Pop2Piano"];
const ZOOMS = [70, 85, 100, 120, 145, 175, 210];

let musicas = [];
let resultados = [];
const pedidos = new Map();   // video_id -> job (desta página)
let nivel = "medio";
try { nivel = localStorage.getItem("partitura.nivel") || "medio"; } catch {}

function aviso(msg, erro = false) {
  const el = $("#aviso");
  el.textContent = msg;
  el.className = erro ? "erro mostrar" : "mostrar";
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => (el.className = ""), 4000);
}
const urlArq = (rel, m) => "/arquivos/" + rel.split("/").map(encodeURIComponent).join("/") + (m ? `?v=${m.mtime}` : "");

// ------------------------------------------------------------------ rotas
function rota() {
  const h = location.hash;
  if (h.startsWith("#/m/")) abrirMusica(decodeURIComponent(h.slice(4)));
  else mostrarInicio();
}
addEventListener("hashchange", rota);

// ------------------------------------------------------------------ início
async function carregarMusicas() {
  try { musicas = (await (await fetch("/api/musicas")).json()).musicas; }
  catch { aviso("Servidor fora do ar?", true); }
  if (!$("#inicio").hidden) desenharInicio();
}

function mostrarInicio() {
  fecharMusica();
  $("#musica").hidden = true;
  $("#inicio").hidden = false;
  document.title = "Partitura";
  desenharInicio();
}

function desenharInicio() {
  const f = semAcento($("#q").value.trim());
  const lib = f ? musicas.filter((m) => semAcento(`${m.titulo} ${m.artista}`).includes(f)) : musicas;
  $("#tituloBib").textContent = f ? "Na sua biblioteca" : "Sua biblioteca";
  $("#secBiblioteca").hidden = f && !lib.length;
  $("#biblioteca").innerHTML = lib.map((m) => `
    <a class="card" href="#/m/${encodeURIComponent(m.pasta)}">
      <div class="capa">${m.capa ? `<img src="${capa(m.capa)}" alt="" loading="lazy">` : ""}</div>
      <div class="info"><b>${esc(m.titulo)}</b><small>${esc(m.artista)}</small></div>
    </a>`).join("") || `<p class="vazio">Nenhuma partitura ainda. Busque uma música acima.</p>`;
  $("#secResultados").hidden = !resultados.length;
  const porVideo = new Map(musicas.filter((m) => m.video_id).map((m) => [m.video_id, m]));
  $("#resultados").innerHTML = resultados.map((v) => {
    const m = porVideo.get(v.id), job = pedidos.get(v.id);
    const acao = m ? `<a class="btn" href="#/m/${encodeURIComponent(m.pasta)}">${icone("biblioteca")}Abrir</a>`
      : job ? `<div class="gerando"><span>${esc(job.etapa || "Na fila")}</span><div class="prog-barra"><i style="width:${job.progresso || 0}%"></i></div></div>`
      : `<button type="button" class="btn primario" data-gerar="${esc(v.id)}">${icone("gerar")}Gerar partitura</button>`;
    return `
    <article class="card res" data-id="${esc(v.id)}">
      <div class="capa"><img src="${esc(v.thumb)}" alt="" loading="lazy">
        <button type="button" class="trecho" data-trecho="${esc(v.id)}" aria-label="Ouvir um trecho">${icone("tocar")}</button>
        <span class="dur">${fmt(v.duracao)}</span></div>
      <div class="info"><b title="${esc(v.titulo_video)}">${esc(v.titulo)}</b><small>${esc(v.artista || v.canal)}</small>${acao}</div>
    </article>`;
  }).join("");
}

$("#q").addEventListener("input", () => {
  if (!$("#q").value.trim()) { resultados = []; $("#status").hidden = true; }
  desenharInicio();
});
$("#formBusca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (q.length < 2) return $("#q").focus();
  $("#q").blur();
  const st = $("#status");
  st.hidden = false;
  st.textContent = "Buscando no YouTube…";
  try {
    const r = await fetch(`/api/busca?q=${encodeURIComponent(q)}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    resultados = d.resultados;
    st.hidden = !!resultados.length;
    st.textContent = "Nada encontrado no YouTube. Tente com o nome do artista.";
  } catch (err) { st.textContent = "Erro na busca: " + err.message; }
  desenharInicio();
});

// trecho de 30 s do YouTube antes de gerar
const trecho = $("#trecho");
let trechoId = null;
$("#resultados").addEventListener("click", async (e) => {
  const t = e.target.closest("[data-trecho]");
  if (t) {
    const id = t.dataset.trecho;
    $$("[data-trecho]").forEach((b) => { b.innerHTML = icone("tocar"); b.classList.remove("tocando"); });
    if (trechoId === id && !trecho.paused) { trecho.pause(); trechoId = null; return; }
    trechoId = id;
    t.innerHTML = icone("carregando");
    trecho.src = `/api/previa/${id}`;
    trecho.play().then(() => { t.innerHTML = icone("pausar"); t.classList.add("tocando"); })
      .catch(() => { t.innerHTML = icone("erro"); });
    return;
  }
  const g = e.target.closest("[data-gerar]");
  if (g) gerar(resultados.find((v) => v.id === g.dataset.gerar));
});
trecho.addEventListener("ended", () => $$("[data-trecho]").forEach((b) => (b.innerHTML = icone("tocar"))));

// ------------------------------------------------------------------ gerar
async function gerar(v) {
  trecho.pause();
  pedidos.set(v.id, { etapa: "Enviando…", progresso: 1 });
  desenharInicio();
  try {
    const r = await fetch("/api/gerar", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: v.id, titulo: v.titulo, artista: v.artista,
                             niveis: ["facil", "medio", "dificil"], versoes: ["AMT-APC"] }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    pedidos.set(v.id, d);
    acompanhar();
  } catch (err) {
    pedidos.delete(v.id);
    aviso("Não deu para gerar: " + err.message, true);
    desenharInicio();
  }
}

let timerPedidos = null;
async function acompanhar() {
  clearTimeout(timerPedidos);
  let jobs = [];
  try { jobs = (await (await fetch("/api/jobs")).json()).jobs; } catch { timerPedidos = setTimeout(acompanhar, 4000); return; }
  const porId = new Map(jobs.map((j) => [j.id, j]));
  let ativo = null;
  for (const [vid, pedido] of [...pedidos]) {
    const j = porId.get(pedido.id);
    if (!j) continue;
    pedidos.set(vid, j);
    if (j.status === "pronto") {
      pedidos.delete(vid);
      await carregarMusicas();
      aviso(`“${j.titulo}” pronta.`);
      if (!$("#inicio").hidden) location.hash = "#/m/" + encodeURIComponent(j.pasta);
    } else if (j.status === "erro") {
      pedidos.delete(vid);
      aviso(`Não deu para gerar “${j.titulo}”: ${j.etapa}`, true);
    } else ativo = ativo || j;
  }
  const barra = $("#progresso");
  barra.hidden = !ativo;
  if (ativo) {
    $("#progTexto").textContent = `Gerando “${ativo.titulo}” · ${ativo.etapa || "na fila"}`;
    $("#progBarra").style.width = `${ativo.progresso || 0}%`;
  }
  if (!$("#inicio").hidden) desenharInicio();
  if (pedidos.size) timerPedidos = setTimeout(acompanhar, 1200);
}

// ------------------------------------------------------------------ música
let atual = null;   // { m, leitor, layout, abort, wake }
const piano = $("#mPiano"), original = $("#mOriginal"), zoom = $("#mZoom"), seguirCaixa = $("#mSeguirCaixa");
zoom.innerHTML = ZOOMS.map((z) => `<option value="${z}" ${z === 100 ? "selected" : ""}>${z}</option>`).join("");
let fonte = piano;

function versaoDe(m, n) { return VERSOES.find((v) => m.arquivos[n]?.[v]); }
function layoutAtual() { return innerWidth >= 1000 ? "pagina" : innerWidth < innerHeight ? "retrato" : "paisagem"; }

async function abrirMusica(pasta) {
  if (!musicas.length) await carregarMusicas();
  const m = musicas.find((x) => x.pasta === pasta);
  if (!m) { aviso("Música não encontrada.", true); location.hash = "#/"; return; }
  trecho.pause();
  $("#inicio").hidden = true;
  $("#musica").hidden = false;
  document.title = `${m.titulo} · Partitura`;
  $("#mTitulo").textContent = m.titulo;
  $("#mArtista").textContent = m.artista || "";
  if (!m.arquivos[nivel]) nivel = ["medio", "facil", "dificil"].find((n) => m.arquivos[n]);
  const continuar = atual?.m.pasta === pasta ? fonte.currentTime : 0;
  fecharMusica(false);
  atual = { m, abort: new AbortController(), layout: null, leitor: null, wake: null };
  $("#mNiveis").innerHTML = Object.entries(NIVEIS).map(([n, nome]) =>
    `<button type="button" data-nivel="${n}" class="${n === nivel ? "ativa" : ""}" ${m.arquivos[n] ? "" : "disabled"}>${nome}</button>`).join("");
  const v = versaoDe(m, nivel), item = m.arquivos[nivel][v];
  piano.src = urlArq(item.previa, m);
  original.src = m.original ? urlArq(m.original, m) : "";
  $("#mFonte").hidden = !m.original;
  fonte = piano;
  if (continuar) piano.addEventListener("loadedmetadata", () => { piano.currentTime = Math.min(continuar, piano.duration || continuar); }, { once: true });
  atual.arquivo = `${m.pasta}/editaveis/${v} - ${NIVEL_ARQ[nivel]}.musicxml`;
  atual.downloads = [
    [item.pdf, "pdf", "Baixar PDF"],
    [`${m.pasta}/editaveis/${v} - ${NIVEL_ARQ[nivel]}.musicxml`, "musicxml", "Baixar MusicXML (MuseScore)"],
    [`${m.pasta}/editaveis/${v} - ${NIVEL_ARQ[nivel]}.mid`, "baixar", "Baixar MIDI"],
  ].filter(([rel]) => rel);
  montarLeitor();
  for (const a of [piano, original])
    for (const t of ["play", "pause", "timeupdate", "ended", "loadedmetadata"])
      a.addEventListener(t, (e) => { if (t === "play") { fonte = e.target; (fonte === piano ? original : piano).pause(); pedirTela(); } pintar(); }, { signal: atual.abort.signal });
  addEventListener("resize", montarLeitor, { signal: atual.abort.signal });
  pintar();
}

function montarLeitor() {
  if (!atual) return;
  const novo = layoutAtual();
  if (novo === atual.layout) return;
  atual.layout = novo;
  atual.leitor?.destruir();
  $("#mArea").innerHTML = "<p>Carregando notas…</p>";
  atual.leitor = new LeitorPartitura({ area: $("#mArea"), audio: piano, original: atual.m.original ? original : null,
    arquivo: atual.arquivo, mostrador: $("#mMostrador"), seguir: seguirCaixa, zoom, layout: novo });
}

function fecharMusica(pararAudio = true) {
  if (!atual) return;
  atual.abort.abort();
  atual.leitor?.destruir();
  atual.wake?.release().catch(() => {});
  if (pararAudio) { piano.pause(); original.pause(); atual = null; }
  $("#mMenu").hidden = true;
}

function pintar() {
  const tocando = !fonte.paused && !fonte.ended;
  $("#mTocar").innerHTML = icone(tocando ? "pausar" : "tocar");
  $("#mTocar").setAttribute("aria-label", tocando ? "Pausar" : "Tocar");
  $("#mRelogio").textContent = `${fmt(fonte.currentTime)} / ${fmt(fonte.duration)}`;
  const pos = $("#mPosicao");
  if (document.activeElement !== pos && fonte.duration) pos.value = Math.round(1000 * fonte.currentTime / fonte.duration);
  $$("#mFonte [data-fonte]").forEach((b) => b.classList.toggle("ativa", (b.dataset.fonte === "original") === (fonte === original)));
}
function tocarPausar() {
  if (fonte.paused) fonte.play().catch(() => {});
  else fonte.pause();
}
function pedirTela() { navigator.wakeLock?.request("screen").then((w) => { if (atual) atual.wake = w; }).catch(() => {}); }

$("#mTocar").addEventListener("click", tocarPausar);
$("#mPosicao").addEventListener("input", () => { if (fonte.duration) fonte.currentTime = $("#mPosicao").value / 1000 * fonte.duration; });
$("#mNiveis").addEventListener("click", (e) => {
  const b = e.target.closest("[data-nivel]");
  if (!b || b.disabled || !atual) return;
  nivel = b.dataset.nivel;
  try { localStorage.setItem("partitura.nivel", nivel); } catch {}
  const tocava = !fonte.paused;
  abrirMusica(atual.m.pasta).then(() => { if (tocava) piano.play().catch(() => {}); });
});
$("#mFonte").addEventListener("click", (e) => {
  const b = e.target.closest("[data-fonte]");
  if (!b) return;
  const nova = b.dataset.fonte === "original" ? original : piano;
  if (nova === fonte) return;
  const tocava = !fonte.paused;
  fonte.pause();
  fonte = nova;
  if (tocava) nova.play().catch(() => {});
  pintar();
});
$(".m-acoes").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.acao === "mais" || b.dataset.acao === "menos") {
    const i = Math.max(0, Math.min(ZOOMS.length - 1, ZOOMS.indexOf(Number(zoom.value)) + (b.dataset.acao === "mais" ? 1 : -1)));
    zoom.value = ZOOMS[i];
    zoom.dispatchEvent(new Event("change"));
  } else if (b.id === "mSeguir") {
    seguirCaixa.checked = !seguirCaixa.checked;
    seguirCaixa.dispatchEvent(new Event("change"));
    b.classList.toggle("ativo", seguirCaixa.checked);
    b.setAttribute("aria-pressed", seguirCaixa.checked);
  } else if (b.id === "mMais") {
    const menu = $("#mMenu");
    if (!menu.hidden) { menu.hidden = true; return; }
    menu.innerHTML = `<button type="button" role="menuitem" data-tela-cheia>${icone("foco")}Tela cheia</button>` +
      (atual?.downloads || []).map(([rel, ic, nome]) => `<a role="menuitem" href="${urlArq(rel, atual.m)}" download>${icone(ic)}${nome}</a>`).join("");
    menu.hidden = false;
  }
});
$("#mMenu").addEventListener("click", (e) => {
  if (e.target.closest("[data-tela-cheia]")) {
    document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.().catch(() => {});
  }
  $("#mMenu").hidden = true;
});
document.addEventListener("click", (e) => {
  if (!e.target.closest("#mMenu, #mMais")) $("#mMenu").hidden = true;
});
// toque no fundo da partitura (fora de nota) esconde/mostra as barras
$("#mArea").addEventListener("click", (e) => {
  if (!e.target.closest(".nota-navegavel") && matchMedia("(pointer: coarse)").matches) $("#musica").classList.toggle("sem-barras");
});
document.addEventListener("keydown", (e) => {
  if ($("#musica").hidden || e.target.closest("input, select, textarea")) return;
  if (e.code === "Space") { e.preventDefault(); tocarPausar(); }
  if (e.code === "Escape") location.hash = "#/";
});

// ------------------------------------------------------------------ começo
carregarMusicas().then(rota);
