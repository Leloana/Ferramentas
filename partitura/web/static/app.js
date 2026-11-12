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
let jobs = [];               // pedidos do servidor (de qualquer aparelho) + o que está sendo enviado daqui
const ativo = (j) => j.status === "fila" || j.status === "rodando";
// etapas da tela de espera: [nome, progresso em que começa] (o servidor marca o progresso, web/servidor._progresso)
const PASSOS = [["Baixando a música", 1], ["Preparando o áudio", 15], ["Detectando o pulso", 20], ["Arranjo com IA", 25],
  ["Detectando os acordes", 55], ["Partitura fácil", 60], ["Partitura média", 69], ["Partitura difícil", 79], ["Piano das prévias", 88]];
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
  else if (h.startsWith("#/g/")) abrirEspera(decodeURIComponent(h.slice(4)));
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
  $("#espera").hidden = true;
  $("#inicio").hidden = false;
  document.title = "Partitura";
  desenharInicio();
  pintarProgresso();
}

// card de uma música sendo gerada: abre a tela de espera
const textoJob = (j) => j.status === "erro" ? "Não deu certo · toque para ver" : j.status === "fila" ? "Na fila" : j.etapa || "Começando…";
function cardJob(j) {
  const erro = j.status === "erro";
  return `
    <a class="card job ${erro ? "falhou" : ""}" data-job="${esc(j.id)}" href="#/g/${encodeURIComponent(j.id)}" aria-label="Ver o andamento de ${esc(j.titulo)}">
      <div class="capa">${j.video_id ? `<img src="${capa(j.video_id)}" alt="" loading="lazy">` : ""}
        <div class="veu">${erro ? icone("erro") : `<span class="girando"></span><span class="pct">${j.progresso || 0}%</span>`}</div></div>
      <div class="info"><b>${esc(j.titulo)}</b>
        <small>${esc(textoJob(j))}</small>
        ${erro ? "" : `<div class="prog-barra"><i style="width:${j.progresso || 0}%"></i></div>`}</div>
    </a>`;
}

function chaveInicio() {
  return JSON.stringify([$("#q").value, musicas.map((m) => m.pasta + m.mtime), resultados.map((v) => v.id),
    jobs.filter((j) => ativo(j) || j.status === "erro").map((j) => j.id + j.status)]);
}
// a cada consulta dos pedidos: atualiza porcentagem, etapa e barra no lugar; redesenha só se a estrutura mudou
function atualizarInicio() {
  if (chaveInicio() !== desenharInicio.chave) return desenharInicio();
  for (const j of jobs) {
    const c = document.querySelector(`.card.job[data-job="${CSS.escape(j.id)}"]`);
    if (!c) continue;
    const pct = c.querySelector(".pct"), barra = c.querySelector(".prog-barra i"), txt = c.querySelector("small");
    if (pct) pct.textContent = `${j.progresso || 0}%`;
    if (barra) barra.style.width = `${j.progresso || 0}%`;
    if (txt && txt.textContent !== textoJob(j)) txt.textContent = textoJob(j);
  }
}

function desenharInicio() {
  desenharInicio.chave = chaveInicio();
  const f = semAcento($("#q").value.trim());
  const casa = (t) => !f || semAcento(t).includes(f);
  const lib = musicas.filter((m) => casa(`${m.titulo} ${m.artista}`));
  const emCurso = jobs.filter((j) => (ativo(j) || j.status === "erro") && casa(`${j.titulo} ${j.artista}`));
  $("#tituloBib").textContent = f ? "Na sua biblioteca" : "Sua biblioteca";
  $("#secBiblioteca").hidden = f && !lib.length && !emCurso.length;
  $("#biblioteca").innerHTML = (emCurso.map(cardJob).join("") + lib.map((m) => `
    <a class="card" href="#/m/${encodeURIComponent(m.pasta)}">
      <div class="capa">${m.capa ? `<img src="${capa(m.capa)}" alt="" loading="lazy">` : ""}
        <button type="button" class="editar" data-renomear="${esc(m.pasta)}" aria-label="Renomear ${esc(m.titulo)}">${icone("editar")}</button></div>
      <div class="info"><b>${esc(m.titulo)}</b><small>${esc(m.artista)}</small></div>
    </a>`).join("")) || `<p class="vazio">Nenhuma partitura ainda. Busque uma música acima.</p>`;
  $("#secResultados").hidden = !resultados.length;
  const porVideo = new Map(musicas.filter((m) => m.video_id).map((m) => [m.video_id, m]));
  $("#resultados").innerHTML = resultados.map((v) => {
    const m = porVideo.get(v.id), job = jobs.find((j) => j.video_id === v.id && ativo(j));
    const acao = job ? `<a class="btn" href="#/g/${encodeURIComponent(job.id)}"><span class="girando"></span>Gerando… ver</a>`
      : m ? `<a class="btn" href="#/m/${encodeURIComponent(m.pasta)}">${icone("biblioteca")}Abrir</a>`
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
// Gerar: volta pra tela principal com o card da música já carregando (toque nele = tela de espera)
async function gerar(v) {
  trecho.pause();
  const temp = { id: `enviando-${v.id}`, video_id: v.id, titulo: v.titulo, artista: v.artista || v.canal || "",
                 status: "fila", etapa: "Enviando…", progresso: 1, local: true };
  jobs.unshift(temp);
  $("#q").value = "";
  resultados = [];
  $("#status").hidden = true;
  if (location.hash && location.hash !== "#/") location.hash = "#/";
  else { desenharInicio(); pintarProgresso(); }
  scrollTo({ top: 0, behavior: "smooth" });
  try {
    const r = await fetch("/api/gerar", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: v.id, titulo: v.titulo, artista: v.artista,
                             niveis: ["facil", "medio", "dificil"], versoes: ["AMT-APC"] }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    jobs = jobs.filter((j) => j !== temp);
    jobs.unshift(d);
    vistos.add(d.id);
    if (location.hash === `#/g/${temp.id}`) location.replace(`#/g/${encodeURIComponent(d.id)}`);
  } catch (err) {
    jobs = jobs.filter((j) => j !== temp);
    aviso("Não deu para gerar: " + err.message, true);
  }
  acompanhar();
}

let timerJobs = null, jobsCarregados = false;
const vistos = new Set();   // pedidos vistos em andamento nesta página (pra avisar quando terminam)
async function acompanhar() {
  clearTimeout(timerJobs);
  let lista;
  try { lista = (await (await fetch("/api/jobs")).json()).jobs; } catch { timerJobs = setTimeout(acompanhar, 4000); return; }
  let recarregar = false;
  jobsCarregados = true;
  for (const j of lista) {
    if (j.status === "pronto") jobsProntos.set(j.id, j.pasta);
    if (vistos.has(j.id) && j.status === "pronto") {
      vistos.delete(j.id);
      recarregar = true;
      aviso(`“${j.titulo}” pronta.`);
      if (location.hash === `#/g/${j.id}`) { await carregarMusicas(); location.replace("#/m/" + encodeURIComponent(j.pasta)); }
    } else if (vistos.has(j.id) && j.status === "erro") {
      vistos.delete(j.id);
      aviso(`Não deu para gerar “${j.titulo}”.`, true);
    }
    if (ativo(j)) vistos.add(j.id);
  }
  jobs = [...jobs.filter((j) => j.local), ...lista.filter((j) => j.status !== "pronto")];
  if (recarregar) await carregarMusicas();
  pintarProgresso();
  if (!$("#inicio").hidden) atualizarInicio();
  if (!$("#espera").hidden) desenharEspera();
  if (jobs.some(ativo)) timerJobs = setTimeout(acompanhar, 1200);
}

// aviso flutuante de geração: só na tela da música (no início o card mostra, na espera a tela toda)
function pintarProgresso() {
  const j = jobs.find(ativo);
  const barra = $("#progresso");
  barra.hidden = !j || $("#musica").hidden;
  if (!j) return;
  barra.dataset.job = j.id;
  $("#progTexto").textContent = `Gerando “${j.titulo}” · ${j.status === "fila" ? "na fila" : j.etapa || "começando"}`;
  $("#progBarra").style.width = `${j.progresso || 0}%`;
}
$("#progresso").addEventListener("click", () => { if ($("#progresso").dataset.job) location.hash = "#/g/" + encodeURIComponent($("#progresso").dataset.job); });

// ------------------------------------------------------------------ espera (música sendo gerada, tela cheia)
let esperaId = null, timerEspera = null;
function abrirEspera(id) {
  fecharMusica();
  trecho.pause();
  esperaId = id;
  $("#inicio").hidden = true;
  $("#musica").hidden = true;
  $("#espera").hidden = false;
  pintarProgresso();
  desenharEspera();
  clearInterval(timerEspera);
  timerEspera = setInterval(() => { if ($("#espera").hidden) clearInterval(timerEspera); else desenharEspera(); }, 1000);
  if (!jobs.length) acompanhar();
}

// troca o HTML só se mudou: reescrever a cada segundo recomeçava a animação de "carregando"
function trocar(sel, html) {
  const el = $(sel);
  if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
}

function desenharEspera() {
  const j = jobs.find((x) => x.id === esperaId);
  if (!j && !jobsCarregados) return;   // abriu direto na espera: espera a lista de pedidos chegar
  if (!j) {   // já terminou (ou o servidor reiniciou): procura a música pronta
    const m = musicas.find((x) => x.pasta && jobsProntos.get(esperaId) === x.pasta);
    location.replace(m ? "#/m/" + encodeURIComponent(m.pasta) : "#/");
    return;
  }
  document.title = `Gerando ${j.titulo} · Partitura`;
  const img = j.video_id ? capa(j.video_id) : "";
  if ($("#eCapa").dataset.src !== img) {
    $("#eCapa").dataset.src = img;
    $("#eCapa").src = img;
    $("#eFundo").style.backgroundImage = img ? `url("${img}")` : "";
  }
  $("#eTitulo").textContent = j.titulo;
  $("#eArtista").textContent = j.artista || "";
  const erro = j.status === "erro", p = erro ? 0 : j.progresso || 0;
  $("#espera").classList.toggle("falhou", erro);
  $("#ePct").textContent = erro ? "" : `${p}%`;
  $("#eBarra").style.width = `${p}%`;
  const frente = jobs.filter((x) => x.status === "rodando" || (x.status === "fila" && x.criado < j.criado)).length;
  $("#eEtapa").textContent = erro ? "Não deu para gerar esta música."
    : j.status === "fila" ? (j.local ? "Enviando o pedido…" : frente ? `Na fila · ${frente} na frente` : "Na fila")
    : j.etapa || "Começando…";
  trocar("#ePassos", erro ? `<li class="msg">${esc(j.etapa)}</li>` : PASSOS.map(([nome, ini], i) => {
    const fim = PASSOS[i + 1]?.[1] ?? 100;
    const estado = j.status !== "rodando" ? "" : p >= fim ? "feito" : p >= ini ? "agora" : "";
    return `<li class="${estado}"><span class="marca">${estado === "feito" ? "✓" : ""}</span>${nome}</li>`;
  }).join(""));
  $("#eTempo").textContent = j.inicio && !erro ? `${fmt(Date.now() / 1000 - j.inicio)} · costuma levar menos de 1 minuto` : "";
  trocar("#eAcoes", erro ? `<button type="button" class="btn primario" data-de-novo>Tentar de novo</button>
    <button type="button" class="btn" data-remover>Remover</button>` : `<a class="btn" href="#/">Voltar pra biblioteca</a>`);
}
const jobsProntos = new Map();   // id do pedido -> pasta (pra quem abre a espera depois de pronto)
$("#eAcoes").addEventListener("click", async (e) => {
  const j = jobs.find((x) => x.id === esperaId);
  if (!j) return;
  if (e.target.closest("[data-remover]") || e.target.closest("[data-de-novo]")) {
    await fetch(`/api/jobs/${encodeURIComponent(j.id)}`, { method: "DELETE" }).catch(() => {});
    jobs = jobs.filter((x) => x !== j);
    if (e.target.closest("[data-de-novo]")) gerar({ id: j.video_id, titulo: j.titulo, artista: j.artista });
    else location.hash = "#/";
  }
});

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
  $("#espera").hidden = true;
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
  pintarProgresso();
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

let arrastando = false;   // a bolinha da posição está sendo arrastada
function pintar() {
  const tocando = !fonte.paused && !fonte.ended;
  $("#mTocar").innerHTML = icone(tocando ? "pausar" : "tocar");
  $("#mTocar").setAttribute("aria-label", tocando ? "Pausar" : "Tocar");
  $("#mRelogio").textContent = `${fmt(fonte.currentTime)} / ${fmt(fonte.duration)}`;
  const pos = $("#mPosicao");
  // só não segue o áudio enquanto o dedo/mouse arrasta (o foco ficava preso no controle depois do 1º toque
  // e a bolinha parava de andar)
  if (!arrastando && fonte.duration) pos.value = Math.round(1000 * fonte.currentTime / fonte.duration);
  $$("#mFonte [data-fonte]").forEach((b) => b.classList.toggle("ativa", (b.dataset.fonte === "original") === (fonte === original)));
}
function tocarPausar() {
  if (fonte.paused) fonte.play().catch(() => {});
  else fonte.pause();
}
function pedirTela() { navigator.wakeLock?.request("screen").then((w) => { if (atual) atual.wake = w; }).catch(() => {}); }

$("#mTocar").addEventListener("click", tocarPausar);
$("#mPosicao").addEventListener("pointerdown", () => { arrastando = true; });
for (const ev of ["pointerup", "pointercancel", "change", "blur"])
  $("#mPosicao").addEventListener(ev, () => { arrastando = false; });
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
    menu.innerHTML = `<button type="button" role="menuitem" data-renomear-atual>${icone("editar")}Renomear</button>` +
      `<button type="button" role="menuitem" data-tela-cheia>${icone("foco")}Tela cheia</button>` +
      (atual?.downloads || []).map(([rel, ic, nome]) => `<a role="menuitem" href="${urlArq(rel, atual.m)}" download>${icone(ic)}${nome}</a>`).join("");
    menu.hidden = false;
  }
});
$("#mMenu").addEventListener("click", (e) => {
  if (e.target.closest("[data-renomear-atual]") && atual) abrirRenomear(atual.m);
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
  if (e.code === "Escape" && $("#renomear").hidden) location.hash = "#/";
});

// ------------------------------------------------------------------ renomear (título e artista mostrados)
let renomeando = null;
function abrirRenomear(m) {
  renomeando = m;
  $("#rnTitulo").value = m.titulo || "";
  $("#rnArtista").value = m.artista || "";
  $("#renomear").hidden = false;
  $("#rnTitulo").focus();
  $("#rnTitulo").select();
}
const fecharRenomear = () => { $("#renomear").hidden = true; renomeando = null; };
$("#biblioteca").addEventListener("click", (e) => {
  const b = e.target.closest("[data-renomear]");
  if (!b) return;
  e.preventDefault();
  e.stopPropagation();
  const m = musicas.find((x) => x.pasta === b.dataset.renomear);
  if (m) abrirRenomear(m);
});
$("#renomear").addEventListener("click", (e) => { if (e.target.id === "renomear" || e.target.closest("[data-fechar]")) fecharRenomear(); });
document.addEventListener("keydown", (e) => { if (e.code === "Escape" && !$("#renomear").hidden) fecharRenomear(); });
$("#formRenomear").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!renomeando) return;
  const m = renomeando, titulo = $("#rnTitulo").value.trim(), artista = $("#rnArtista").value.trim();
  if (!titulo) return $("#rnTitulo").focus();
  try {
    const r = await fetch(`/api/musicas/${encodeURIComponent(m.pasta)}/renomear`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ titulo, artista }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    m.titulo = d.titulo;
    m.artista = d.artista;
    if (atual?.m === m) {
      $("#mTitulo").textContent = m.titulo;
      $("#mArtista").textContent = m.artista;
      document.title = `${m.titulo} · Partitura`;
    }
    fecharRenomear();
    if (!$("#inicio").hidden) desenharInicio();
    aviso("Nome salvo.");
  } catch (err) { aviso("Não deu para renomear: " + err.message, true); }
});

// ------------------------------------------------------------------ começo
Promise.all([carregarMusicas(), acompanhar()]).then(rota);
