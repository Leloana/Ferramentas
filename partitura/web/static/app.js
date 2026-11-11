// Partitura — front-end (vanilla JS)
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const NIVEL_NOME = { facil: "Fácil", medio: "Médio", dificil: "Difícil" };
// Revisão de 120 partituras: preservar melodia/letra e também trechos instrumentais.
// Revisão às cegas 2026-11-10: o médio Híbrido é a base e fácil/difícil saem dele: Híbrido (AMT) nos três.
const PADRAO = { facil: "HibridoAMT", medio: "HibridoAMT", dificil: "HibridoAMT" };
const VERSAO_NOME = { HibridoAMT: "Híbrido (AMT)", Hibrido: "Híbrido (Pop2Piano)", Acordes: "Acordes", Pop2Piano: "Pop2Piano", "AMT-APC": "AMT-APC" };
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const urlArq = (rel) => {
  const m = musicas.find((m) => rel.startsWith(m.pasta + "/"));
  return "/arquivos/" + rel.split("/").map(encodeURIComponent).join("/") + (m ? `?v=${m.mtime}` : "");
};
const TEOR_NOME = { calma: "calma", lenta: "lenta", emotiva: "emotiva", animada: "animada", epica: "épica" };
const tempoDecorrido = (seg) => (seg >= 3600 ? `${Math.floor(seg / 3600)}h${String(Math.floor(seg % 3600 / 60)).padStart(2, "0")}` : dur(Math.max(1, seg)));
const dur = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "");

let musicas = [];
let selecionada = null;
let leitorPartitura = null;
let escolha = { nivel: "medio", versao: "HibridoAMT" };
try { escolha = { ...escolha, ...JSON.parse(localStorage.getItem("partitura.escolha") || "{}") }; } catch {}

// ------------------------------------------------------------------ abas
function abrirAba(nome) {
  if (location.hash.slice(1) !== nome) history.replaceState(null, "", "#" + nome);
  $$(".aba").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
  $$(".painel").forEach((p) => p.classList.toggle("ativo", p.id === nome));
  if (nome === "biblioteca") carregarMusicas();
  if (nome === "fila") carregarJobs();
  if (nome === "karaoke") carregarKaraoke();
}
$$(".aba").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.aba)));

// ------------------------------------------------------------------ busca
const player = $("#player");
let tocandoId = null;

const icone = (nome, cls = "ic") => `<svg class="${cls}" aria-hidden="true"><use href="icones/sprite.svg#i-${nome}"/></svg>`;
const ICONE_TOCAR = icone("tocar"), ICONE_PAUSAR = icone("pausar"), ICONE_CARREGANDO = icone("carregando");

$$("#sugestoes [data-q]").forEach((b) => b.addEventListener("click", () => {
  $("#q").value = b.dataset.q;
  $("#formBusca").requestSubmit();
}));

$("#formBusca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (q.length < 2) { $("#q").focus(); return; }
  $("#hero").classList.add("compacto");
  $("#recentes").hidden = true;
  $("#statusBusca").textContent = "";
  $("#resultados").innerHTML = Array.from({ length: 8 }, () => `
    <article class="res esqueleto" aria-hidden="true"><div class="capa"></div>
      <div class="info"><div class="linha-esq" style="width:90%"></div><div class="linha-esq" style="width:55%"></div></div></article>`).join("");
  try {
    const r = await fetch(`/api/busca?q=${encodeURIComponent(q)}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "erro");
    $("#statusBusca").textContent = d.resultados.length ? "" : "Nada encontrado. Tente com o nome do artista.";
    const jaTem = new Set(musicas.map((m) => m.video_id).filter(Boolean));
    $("#resultados").innerHTML = d.resultados.map((v, i) => `
      <article class="res" data-id="${esc(v.id)}" style="animation-delay:${i * 40}ms">
        <div class="capa">
          <img src="${esc(v.thumb)}" alt="" loading="lazy">
          ${jaTem.has(v.id) ? `<span class="ja">${icone("ok")}na biblioteca</span>` : ""}
          <button class="tocar" title="Ouvir um trecho" aria-label="Ouvir um trecho">${ICONE_TOCAR}</button>
          <span class="dur">${dur(v.duracao)}</span>
        </div>
        <div class="info">
          <h3 title="${esc(v.titulo_video)}">${esc(v.titulo_video)}</h3>
          <span class="canal">${esc(v.canal)}</span>
          <button class="btn primario gerar">${icone("gerar")}Gerar partitura</button>
        </div>
      </article>`).join("");
    $$(".res").forEach((el, i) => {
      const v = d.resultados[i];
      $(".tocar", el).addEventListener("click", () => tocar(v.id, $(".tocar", el)));
      $(".gerar", el).addEventListener("click", () => abrirDialogo(v));
    });
  } catch (err) {
    $("#resultados").innerHTML = "";
    $("#statusBusca").textContent = "Erro na busca: " + err.message;
  }
});
// apagar a busca volta para a tela inicial
$("#q").addEventListener("input", () => {
  if ($("#q").value) return;
  $("#hero").classList.remove("compacto");
  $("#resultados").innerHTML = "";
  $("#statusBusca").textContent = "";
  desenharRecentes();
});

function desenharRecentes() {
  const lista = musicas.slice(0, 6);
  $("#recentes").hidden = !lista.length || !!$("#resultados").children.length;
  $("#listaRecentes").innerHTML = lista.map((m) => `
    <button type="button" data-pasta="${esc(m.pasta)}">
      ${m.video_id ? `<img src="https://i.ytimg.com/vi/${esc(m.video_id)}/mqdefault.jpg" alt="">` : '<img alt="">'}
      <span><b>${esc(m.titulo)}</b><small>${esc(m.artista)}</small></span>
    </button>`).join("");
  $$("#listaRecentes [data-pasta]").forEach((b) => b.addEventListener("click", () => {
    abrirAba("biblioteca");
    selecionar(b.dataset.pasta);
  }));
}

function tocar(id, botao) {
  $("#audioPartitura")?.pause();
  $("#audioOriginal")?.pause();
  $$(".tocar").forEach((b) => { b.innerHTML = ICONE_TOCAR; b.classList.remove("carregando", "tocando"); });
  if (tocandoId === id && !player.paused) { player.pause(); tocandoId = null; return; }
  tocandoId = id;
  botao.classList.add("carregando");
  botao.innerHTML = ICONE_CARREGANDO;
  player.src = `/api/previa/${id}`;
  player.play().then(() => { botao.classList.remove("carregando"); botao.classList.add("tocando"); botao.innerHTML = ICONE_PAUSAR; })
    .catch(() => { botao.classList.remove("carregando"); botao.innerHTML = icone("erro"); });
}
player.addEventListener("ended", () => $$(".tocar").forEach((b) => { b.innerHTML = ICONE_TOCAR; b.classList.remove("tocando"); }));

// ------------------------------------------------------------------ diálogo de geração
let videoAtual = null;
$("#gEstilo").innerHTML = Array.from({ length: 21 }, (_, i) =>
  `<option value="${i + 1}">Estilo ${i + 1}${i === 0 ? " (padrão)" : ""}</option>`).join("");
function atualizarEstilo() {
  const usa = $$('input[name="versao"]:checked').some((i) => ["Hibrido", "Pop2Piano"].includes(i.value));
  $("#gEstilo").disabled = !usa;
  $("#linhaEstilo").hidden = !usa;
  $("#ajudaEstilo").hidden = !usa;
}
$$('input[name="versao"]').forEach((i) => i.addEventListener("change", atualizarEstilo));
atualizarEstilo();
// o idioma japonês tem a escolha de escrita (romaji ou kana)
function atualizarEscrita() { $("#linhaEscrita").hidden = $("#gIdioma").value !== "ja"; }
$("#gIdioma").addEventListener("change", atualizarEscrita);
const radio = (nome) => $(`input[name="${nome}"]:checked`)?.value || "";
// lembra as escolhas do último pedido (níveis, versões, teores, idioma)
const CAMPOS_PEDIDO = ["gIdioma", "gEscrita", "gEstilo", "gSeparador"];
function guardarPedido() {
  const d = { nivel: $$('input[name="nivel"]:checked').map((i) => i.value),
              versao: $$('input[name="versao"]:checked').map((i) => i.value),
              intro: radio("intro"), final: radio("final"), acomp: radio("acomp") };
  CAMPOS_PEDIDO.forEach((id) => (d[id] = $("#" + id).value));
  try { localStorage.setItem("partitura.pedido", JSON.stringify(d)); } catch {}
}
function restaurarPedido() {
  let d;
  try { d = JSON.parse(localStorage.getItem("partitura.pedido") || "null"); } catch {}
  if (!d) return;
  ["nivel", "versao"].forEach((n) => Array.isArray(d[n]) && $$(`input[name="${n}"]`).forEach((i) => (i.checked = d[n].includes(i.value))));
  ["intro", "final", "acomp"].forEach((n) => { const i = $(`input[name="${n}"][value="${d[n] || ""}"]`); if (i) i.checked = true; });
  CAMPOS_PEDIDO.forEach((id) => { if (d[id] && $(`#${id} option[value="${d[id]}"]`)) $("#" + id).value = d[id]; });
}
restaurarPedido();
atualizarEstilo();
atualizarEscrita();
function abrirDialogo(v) {
  videoAtual = v;
  $("#gThumb").src = v.thumb;
  $("#gVideo").textContent = `${v.titulo_video} · ${v.canal}`;
  $("#gTitulo").value = v.titulo;
  $("#gArtista").value = v.artista;
  $("#dlgGerar").showModal();
}
// Enter em qualquer campo = "Gerar partitura" (antes o Enter acionava o primeiro botão, "Cancelar",
// e o pedido sumia sem aviso). Cancelar é type="button" e só fecha.
$("#gCancelar").addEventListener("click", () => $("#dlgGerar").close());
$("#formGerar").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!videoAtual) return;
  const botao = $("#gOk");
  botao.disabled = true;
  botao.textContent = "Enviando…";
  try { await enviarPedido(); } finally { botao.disabled = false; botao.innerHTML = icone("gerar") + "<span>Gerar partitura</span>"; }
});
async function enviarPedido() {
  const niveis = $$('input[name="nivel"]:checked').map((i) => i.value);
  const versoes = $$('input[name="versao"]:checked').map((i) => i.value);
  const corpo = {
    video_id: videoAtual.id, titulo: $("#gTitulo").value.trim(), artista: $("#gArtista").value.trim(),
    niveis: niveis.length ? niveis : ["medio"], versoes: versoes.length ? versoes : ["Hibrido"],
    idioma: $("#gIdioma").value,
    escrita_ja: $("#gEscrita").value,
    estilo: Number($("#gEstilo").value),
    separador: $("#gSeparador").value,
    introducao: radio("intro"),
    final: radio("final"),
    acompanhamento: radio("acomp"),
  };
  guardarPedido();
  let r;
  try {
    r = await fetch("/api/gerar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  } catch {
    aviso("Servidor fora do ar? Não consegui enviar o pedido.", true);
    return;
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    aviso("Não deu para pedir a geração: " + (d.detail || r.status), true);
    return;
  }
  $("#dlgGerar").close();
  aviso(`“${corpo.titulo}” entrou na fila.`);
  abrirAba("fila");
}
function aviso(msg, erro = false) {
  let el = $("#aviso");
  if (!el) { el = document.createElement("div"); el.id = "aviso"; document.body.appendChild(el); }
  el.textContent = msg;
  el.className = erro ? "erro mostrar" : "mostrar";
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => el.classList.remove("mostrar"), 4000);
}
function alertaSuave(msg) { aviso(msg, true); }

// ------------------------------------------------------------------ fila
let timerFila = null;
let jobsAtuais = [];
function linhaJob(j) {
  const agora = Date.now() / 1000;
  const tempo = j.status === "rodando" ? ` · ${tempoDecorrido(agora - (j.inicio || agora))}`
    : j.status === "pronto" && j.fim && j.inicio ? ` · levou ${tempoDecorrido(j.fim - j.inicio)}` : "";
  const teores = [["intro", j.introducao], ["final", j.final], ["acomp.", j.acompanhamento]]
    .filter(([, t]) => t).map(([n, t]) => `${n} ${TEOR_NOME[t] || t}`);
  const estado = j.status === "pronto" ? `${icone("ok")} Pronto` : j.status === "erro" ? `${icone("erro")} ${esc(j.etapa)}`
    : j.status === "fila" ? `${icone("relogio")} ${esc(j.etapa)}` : esc(j.etapa);
  return `
    <div class="job ${j.status}">
      <div class="cab">
        <h3>${esc(j.titulo)} <small class="etapa">${esc(j.artista)}</small></h3>
        <span class="etapa">${j.niveis.map((n) => NIVEL_NOME[n]).join(", ")} · ${j.versoes.map((v) => VERSAO_NOME[v] || v).join(", ")}${teores.length ? " · " + esc(teores.join(", ")) : ""}${j.reusar_cache ? ` · variação ${j.variacao}` : ""}</span>
      </div>
      <div class="barra"><div style="width:${j.progresso}%"></div></div>
      <div class="cab">
        <span class="etapa tempo">${estado}${j.status === "rodando" ? ` · ${j.progresso}%` : ""}${tempo}</span>
        <span class="acoes">
          ${j.status === "pronto" ? `<button class="btn pequeno" data-abrir="${esc(j.pasta)}">${icone("biblioteca")}Abrir partitura</button>` : ""}
          ${j.status === "fila" ? `<button class="btn pequeno discreto" data-tirar="${j.id}">Cancelar</button>` : ""}
          ${j.status === "pronto" || j.status === "erro" ? `<button class="btn pequeno discreto" data-tirar="${j.id}" title="Tirar da lista">Tirar</button>` : ""}
        </span>
      </div>
      ${j.log.length ? `<details ${j.status === "erro" ? "open" : ""}><summary class="etapa">detalhes</summary><pre>${esc(j.log.join("\n"))}</pre></details>` : ""}
    </div>`;
}
async function carregarJobs() {
  let d;
  try { d = await (await fetch("/api/jobs")).json(); } catch { clearTimeout(timerFila); timerFila = setTimeout(carregarJobs, 5000); return; }
  jobsAtuais = d.jobs;
  const ativos = d.jobs.filter((j) => j.status === "fila" || j.status === "rodando").length;
  $("#contFila").textContent = ativos ? `(${ativos})` : "";
  $("#limparFila").hidden = !d.jobs.some((j) => j.status === "pronto" || j.status === "erro");
  // não redesenha enquanto a pessoa lê os detalhes de um pedido aberto
  const abertos = new Set($$("#listaJobs details[open]").map((x) => x.closest(".job")?.querySelector("h3")?.textContent));
  $("#listaJobs").innerHTML = d.jobs.length ? d.jobs.map(linhaJob).join("")
    : '<p class="vazio-msg">Nenhum pedido ainda. Busque uma música e clique em “Gerar partitura”.</p>';
  $$("#listaJobs .job").forEach((el) => { if (abertos.has($("h3", el)?.textContent)) $("details", el)?.setAttribute("open", ""); });
  $$("[data-abrir]").forEach((b) => b.addEventListener("click", async () => {
    abrirAba("biblioteca");
    await carregarMusicas();
    selecionar(b.dataset.abrir);
  }));
  $$("[data-tirar]").forEach((b) => b.addEventListener("click", () => tirarJob(b.dataset.tirar)));
  clearTimeout(timerFila);
  if (ativos) timerFila = setTimeout(() => { carregarJobs(); if ($("#biblioteca").classList.contains("ativo")) carregarMusicas(); }, 2000);
}
async function tirarJob(id) {
  const r = await fetch(`/api/jobs/${id}`, { method: "DELETE" }).catch(() => null);
  if (!r || !r.ok) { const d = await r?.json().catch(() => ({})); aviso(d?.detail || "Não consegui tirar o pedido.", true); }
  carregarJobs();
}
$("#limparFila").addEventListener("click", async () => {
  await Promise.all(jobsAtuais.filter((j) => j.status === "pronto" || j.status === "erro")
    .map((j) => fetch(`/api/jobs/${j.id}`, { method: "DELETE" }).catch(() => null)));
  carregarJobs();
});

// ------------------------------------------------------------------ biblioteca
async function carregarMusicas() {
  let d;
  try { d = await (await fetch("/api/musicas")).json(); } catch { aviso("Servidor fora do ar?", true); return; }
  const mudou = JSON.stringify(d.musicas) !== JSON.stringify(musicas);
  musicas = d.musicas;
  $("#contBib").textContent = musicas.length ? `(${musicas.length})` : "";
  if (mudou || !$("#listaMusicas").children.length) desenharLista();
  if (mudou || !$("#listaRecentes").children.length) desenharRecentes();
  if (!selecionada && musicas.length) selecionar(musicas[0].pasta);
}
const semAcento = (t) => String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
function desenharLista() {
  const f = semAcento($("#filtroBib").value.trim());
  const lista = f ? musicas.filter((m) => semAcento(`${m.titulo} ${m.artista}`).includes(f)) : musicas;
  $("#listaMusicas").innerHTML = lista.map((m) => `
    <button class="mus ${selecionada === m.pasta ? "ativa" : ""}" data-pasta="${esc(m.pasta)}">
      ${m.video_id ? `<img src="https://i.ytimg.com/vi/${m.video_id}/mqdefault.jpg" alt="">` : '<img alt="">'}
      <span><b>${esc(m.titulo)}</b><small>${esc(m.artista)}</small></span>
    </button>`).join("") || `<p class="vazio-msg">${f ? "Nada com esse nome." : "Nenhuma partitura ainda. Busque uma música na aba Buscar."}</p>`;
  $$(".mus").forEach((b) => b.addEventListener("click", () => selecionar(b.dataset.pasta)));
}
$("#filtroBib").addEventListener("input", desenharLista);

function selecionar(pasta) {
  selecionada = pasta;
  $$(".mus").forEach((b) => b.classList.toggle("ativa", b.dataset.pasta === pasta));
  desenharVisor();
}

function desenharVisor() {
  leitorPartitura?.destruir();
  leitorPartitura = null;
  const m = musicas.find((x) => x.pasta === selecionada);
  const visor = $("#visor");
  if (!m) { visor.className = "visor vazio"; visor.innerHTML = "<p>Escolha uma música à esquerda.</p>"; return; }
  visor.className = "visor";
  const niveis = ["facil", "medio", "dificil"].filter((n) => m.arquivos[n]);
  if (!m.arquivos[escolha.nivel]) escolha.nivel = niveis.includes("medio") ? "medio" : niveis[0];
  const versoes = ["HibridoAMT", "Hibrido", "Acordes", "Pop2Piano", "AMT-APC"].filter((v) => m.arquivos[escolha.nivel][v]);
  if (!m.arquivos[escolha.nivel][escolha.versao]) escolha.versao = versoes[0];
  try { localStorage.setItem("partitura.escolha", JSON.stringify(escolha)); } catch {}
  const item = m.arquivos[escolha.nivel][escolha.versao] || {};
  visor.innerHTML = `
    <div class="visor-cab">
      <div><h2>${esc(m.titulo)}</h2><p class="art">${esc(m.artista)}${m.atualizado ? ` <span class="atualizado">· gerada em ${esc(m.atualizado)}</span>` : ""}</p></div>
      ${(m.introducao || m.final) ? `<button type="button" id="outraVariacao" class="btn pequeno" title="Gera outra introdução/final; a atual fica guardada">${icone("variacao")}Outra variação</button>` : ""}
    </div>
    ${(m.introducao || m.final || m.acompanhamento) ? `<div class="etiquetas">
      ${m.introducao ? `<span class="etiqueta">introdução <b>${TEOR_NOME[m.introducao] || esc(m.introducao)}</b></span>` : ""}
      ${m.final ? `<span class="etiqueta">final <b>${TEOR_NOME[m.final] || esc(m.final)}</b></span>` : ""}
      ${m.acompanhamento ? `<span class="etiqueta">acompanhamento <b>${TEOR_NOME[m.acompanhamento] || esc(m.acompanhamento)}</b></span>` : ""}
      ${(m.introducao || m.final) ? `<span class="etiqueta" title="${m.variacoes?.length ? "anteriores em variacoes/: " + esc(m.variacoes.join(", ")) : ""}">variação <b>${m.variacao || 0}</b>${m.variacoes?.length ? ` · ${m.variacoes.length} guardada${m.variacoes.length > 1 ? "s" : ""}` : ""}</span>` : ""}
    </div>` : ""}
    <div class="seletor">
      <div class="grupo">${["facil", "medio", "dificil"].map((n) => `<button data-nivel="${n}" class="${n === escolha.nivel ? "ativa" : ""}" ${m.arquivos[n] ? "" : "disabled"}>${NIVEL_NOME[n]}</button>`).join("")}</div>
      <div class="grupo">${["HibridoAMT", "Hibrido", "Acordes", "Pop2Piano", "AMT-APC"].map((v) => `<button data-versao="${v}" class="${v === escolha.versao ? "ativa" : ""}" ${m.arquivos[escolha.nivel][v] ? "" : "disabled"} title="${PADRAO[escolha.nivel] === v ? "recomendada para este nível" : ""}">${VERSAO_NOME[v]}${PADRAO[escolha.nivel] === v ? " ★" : ""}</button>`).join("")}</div>
    </div>
    <div class="audios">
      ${item.previa ? `<div><label>${icone("piano")} Como soa esta partitura (piano)</label><audio id="audioPartitura" controls preload="metadata" src="${urlArq(item.previa)}"></audio></div>` : ""}
      ${m.original ? `<div><label>${icone("fone")} Gravação original</label><audio id="audioOriginal" controls preload="none" src="${urlArq(m.original)}"></audio></div>` : ""}
    </div>
    ${item.previa ? `<div class="controles-partitura">
      <button type="button" id="abrirFoco" class="btn pequeno primario">${icone("foco")}Modo foco</button>
      <label><input type="checkbox" id="seguirPartitura" checked> Acompanhar piano</label>
      <label>Zoom <select id="zoomPartitura"><option value="100">100%</option><option value="125">125%</option><option value="150">150%</option><option value="200">200%</option></select></label>
      <span id="tempoPartitura">Preparando partitura…</span>
    </div><div id="partituraInterativa" class="partitura-interativa" aria-label="Partitura sincronizada com o piano"><p>Carregando notas…</p></div>` : ""}
    ${item.pdf ? `<details class="pdf-alternativo" ${item.previa ? "" : "open"}><summary>Ver PDF estático</summary><iframe loading="lazy" title="PDF da partitura" class="pdf" src="${urlArq(item.pdf)}#view=FitH"></iframe></details>` : "<p>Sem PDF para esta combinação.</p>"}
    <div class="links">
      ${item.pdf ? `<a href="${urlArq(item.pdf)}" target="_blank">${icone("pdf")}abrir PDF em nova aba</a>` : ""}
      ${m.editaveis.filter((e) => e.includes(`${escolha.versao} - ${{ facil: "Facil", medio: "Medio", dificil: "Dificil" }[escolha.nivel]}`))
        .map((e) => `<a href="${urlArq(e)}" download>${icone("musicxml")}baixar MusicXML (MuseScore)</a>`).join("")}
    </div>`;
  const audio = $("#audioPartitura", visor), original = $("#audioOriginal", visor);
  if (audio) {
    const arquivo = `${m.pasta}/editaveis/${escolha.versao} - ${{facil:"Facil",medio:"Medio",dificil:"Dificil"}[escolha.nivel]}.musicxml`;
    const criarLeitor = () => (leitorPartitura = new LeitorPartitura({ area: $("#partituraInterativa",visor), audio, original, arquivo,
      mostrador: $("#tempoPartitura",visor), seguir: $("#seguirPartitura",visor), zoom: $("#zoomPartitura",visor) }));
    criarLeitor();
    $("#abrirFoco", visor).addEventListener("click", () => abrirFoco({ m, audio, original, arquivo, aoSair: criarLeitor }));
    // o leitor segue o que estiver tocando (o original só se a música tiver o mapa de batidas)
    audio.addEventListener('play', () => { original?.pause(); player.pause(); });
    original?.addEventListener('play', () => { audio.pause(); player.pause(); });
  }
  $("#outraVariacao", visor)?.addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    try {
      const r = await fetch("/api/variacao", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ pasta: m.pasta }) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Não consegui pedir outra variação.");
      aviso(`Gerando a variação ${d.variacao}; a atual fica guardada.`);
      abrirAba("fila");
    } catch (e) { aviso(e.message, true); ev.target.disabled = false; }
  });
  $$("[data-nivel]", visor).forEach((b) => b.addEventListener("click", () => {
    escolha.nivel = b.dataset.nivel;
    // ao trocar de nível, vai pra versão recomendada dele (análise de 7 músicas, ver README)
    if (m.arquivos[escolha.nivel]?.[PADRAO[escolha.nivel]]) escolha.versao = PADRAO[escolha.nivel];
    desenharVisor();
  }));
  $$("[data-versao]", visor).forEach((b) => b.addEventListener("click", () => { escolha.versao = b.dataset.versao; desenharVisor(); }));
}

// ------------------------------------------------------------------ modo foco
// Partitura em tela cheia, desenhada estreita no celular (poucos compassos por linha, pauta
// grande), com uma barra de controle para o dedo. Tocar no fundo esconde/mostra as barras.
let focoAtual = null;
const ZOOMS = [70, 85, 100, 120, 145, 175, 210];
function layoutFoco() {
  if (innerWidth >= 1000) return "pagina";
  return innerWidth < innerHeight ? "retrato" : "paisagem";
}
function abrirFoco({ m, audio, original, arquivo, aoSair }) {
  leitorPartitura?.destruir();
  leitorPartitura = null;
  const el = document.createElement("div");
  el.className = "foco";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "Modo foco: " + m.titulo);
  el.innerHTML = `
    <div class="foco-topo">
      <div class="foco-titulo"><b>${esc(m.titulo)}</b><small>${NIVEL_NOME[escolha.nivel]} · ${VERSAO_NOME[escolha.versao]}</small></div>
      <button type="button" class="foco-btn" data-acao="sair" aria-label="Sair do modo foco">${icone("sair")}</button>
    </div>
    <div class="partitura-interativa foco-area"><p>Carregando notas…</p></div>
    <div class="foco-barra">
      <button type="button" class="foco-play" data-acao="tocar" aria-label="Tocar">${ICONE_TOCAR}</button>
      <div class="foco-tempo">
        <input type="range" min="0" max="1000" value="0" aria-label="Posição na música">
        <span class="foco-relogio">0:00 / 0:00</span>
      </div>
      ${original ? `<div class="grupo foco-fonte" role="group" aria-label="O que tocar">
        <button type="button" data-fonte="piano" class="ativa">${icone("piano")}<span>Piano</span></button>
        <button type="button" data-fonte="original">${icone("fone")}<span>Original</span></button></div>` : ""}
      <div class="foco-zoom">
        <button type="button" class="foco-btn" data-acao="menos" aria-label="Diminuir">${icone("menos")}</button>
        <button type="button" class="foco-btn" data-acao="mais" aria-label="Aumentar">${icone("mais")}</button>
      </div>
      <label class="foco-seguir"><input type="checkbox" checked> Seguir</label>
      <button type="button" class="foco-btn foco-sair-barra" data-acao="sair" aria-label="Sair do modo foco">${icone("sair")}</button>
      <select hidden>${ZOOMS.map((z) => `<option value="${z}" ${z === 100 ? "selected" : ""}>${z}</option>`).join("")}</select>
      <span hidden class="foco-mostrador"></span>
    </div>`;
  document.body.appendChild(el);
  document.body.classList.add("em-foco");
  const area = $(".foco-area", el), zoom = $("select", el), seguir = $(".foco-seguir input", el);
  const barra = $('input[type="range"]', el), relogio = $(".foco-relogio", el), play = $('[data-acao="tocar"]', el);
  let fonte = !audio.paused || !original ? audio : (!original.paused ? original : audio);
  let leitor = null, layout = null, wake = null;
  const abort = new AbortController();
  const montar = () => {
    const novo = layoutFoco();
    if (novo === layout) return;
    layout = novo;
    leitor?.destruir();
    area.innerHTML = "<p>Carregando notas…</p>";
    leitor = new LeitorPartitura({ area, audio, original, arquivo, mostrador: $(".foco-mostrador", el), seguir, zoom, layout });
  };
  montar();
  const fmt = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");
  const pintar = () => {
    const tocando = !fonte.paused && !fonte.ended;
    play.innerHTML = tocando ? ICONE_PAUSAR : ICONE_TOCAR;
    play.setAttribute("aria-label", tocando ? "Pausar" : "Tocar");
    relogio.textContent = `${fmt(fonte.currentTime)} / ${fmt(fonte.duration)}`;
    if (document.activeElement !== barra && fonte.duration) barra.value = Math.round(1000 * fonte.currentTime / fonte.duration);
    $$("[data-fonte]", el).forEach((b) => b.classList.toggle("ativa", (b.dataset.fonte === "original") === (fonte === original)));
  };
  for (const a of [audio, original].filter(Boolean))
    for (const t of ["play", "pause", "timeupdate", "ended", "loadedmetadata"])
      a.addEventListener(t, (e) => { if (t === "play") fonte = e.target; pintar(); }, { signal: abort.signal });
  const tocarPausar = () => {
    if (fonte.paused) { (fonte === audio ? original : audio)?.pause(); player.pause(); fonte.play().catch(() => {}); }
    else fonte.pause();
  };
  barra.addEventListener("input", () => { if (fonte.duration) fonte.currentTime = barra.value / 1000 * fonte.duration; });
  const mudarZoom = (passo) => {
    const i = Math.max(0, Math.min(ZOOMS.length - 1, ZOOMS.indexOf(Number(zoom.value)) + passo));
    zoom.value = ZOOMS[i];
    zoom.dispatchEvent(new Event("change"));
  };
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b?.dataset.acao === "sair") return sair();
    if (b?.dataset.acao === "tocar") return tocarPausar();
    if (b?.dataset.acao === "mais") return mudarZoom(1);
    if (b?.dataset.acao === "menos") return mudarZoom(-1);
    if (b?.dataset.fonte) {
      const nova = b.dataset.fonte === "original" ? original : audio;
      if (nova !== fonte) { const tocava = !fonte.paused; fonte.pause(); fonte = nova; if (tocava) nova.play().catch(() => {}); pintar(); }
      return;
    }
    // toque no fundo (fora de nota) esconde/mostra as barras
    if (e.target.closest(".foco-area") && !e.target.closest(".nota-navegavel")) el.classList.toggle("sem-barras");
  }, { signal: abort.signal });
  addEventListener("resize", montar, { signal: abort.signal });
  // tela acesa enquanto lê; volta a pedir quando a aba volta a aparecer
  const pedirTela = () => navigator.wakeLock?.request("screen").then((w) => (wake = w)).catch(() => {});
  pedirTela();
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") pedirTela(); }, { signal: abort.signal });
  // botão voltar do celular sai do foco
  history.pushState({ foco: true }, "");
  addEventListener("popstate", () => sair(true), { signal: abort.signal });
  if (matchMedia("(pointer: coarse)").matches) document.documentElement.requestFullscreen?.().catch(() => {});
  function sair(peloVoltar = false) {
    abort.abort();
    leitor?.destruir();
    wake?.release().catch(() => {});
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    el.remove();
    document.body.classList.remove("em-foco");
    focoAtual = null;
    if (!peloVoltar && history.state?.foco) history.back();
    aoSair();
  }
  focoAtual = { sair: () => sair(), tocarPausar };
  pintar();
}

// espaço toca/pausa a prévia de piano na biblioteca (fora de campos de texto)
document.addEventListener("keydown", (e) => {
  if (e.code === "Escape" && focoAtual) { focoAtual.sair(); return; }
  if (e.code === "Space" && focoAtual && !e.target.closest("button, input")) { e.preventDefault(); focoAtual.tocarPausar(); return; }
  if (e.code !== "Space" || e.repeat || !$("#biblioteca").classList.contains("ativo")) return;
  if (e.target.closest("input, select, textarea, button, audio, dialog[open]")) return;
  const a = $("#audioPartitura");
  if (!a) return;
  e.preventDefault();
  a.paused ? a.play() : a.pause();
});

carregarMusicas();
carregarJobs();


// ------------------------------------------------------------------ karaokê
let karaoke = [];
async function carregarKaraoke() {
  try { karaoke = await (await fetch("/api/karaoke")).json(); } catch { aviso("Servidor fora do ar?", true); return; }
  $("#contKar").textContent = karaoke.length || "";
  desenharKaraoke();
}
function desenharKaraoke() {
  const f = semAcento($("#filtroKar").value);
  const norm = semAcento;
  const lista = karaoke.filter((m) => !f || norm(m.titulo + " " + m.artista).includes(f));
  $("#listaKar").innerHTML = lista.map((m) => `
    <div class="kar" data-slug="${esc(m.slug)}">
      <span class="kar-txt"><b>${esc(m.titulo)}</b><small>${esc(m.artista)}${m.pasta ? " · na biblioteca" : ""}</small></span>
      ${m.pasta ? `<button type="button" class="btn pequeno discreto kar-abrir" data-pasta="${esc(m.pasta)}">Abrir</button>` : ""}
      <button type="button" class="btn pequeno ${m.pasta ? "" : "primario"} kar-gerar">${icone("gerar")}<span>${m.pasta ? "Gerar de novo" : "Gerar"}</span></button>
    </div>`).join("") || `<p class="status">Nenhuma música encontrada.</p>`;
}
$("#filtroKar").addEventListener("input", desenharKaraoke);
$("#listaKar").addEventListener("click", async (ev) => {
  const linha = ev.target.closest(".kar");
  if (!linha) return;
  if (ev.target.closest(".kar-abrir")) {
    abrirAba("biblioteca");
    const pasta = ev.target.closest(".kar-abrir").dataset.pasta;
    setTimeout(() => { const b = [...document.querySelectorAll("#listaMusicas [data-pasta]")].find((x) => x.dataset.pasta === pasta); if (b) b.click(); }, 400);
    return;
  }
  if (!ev.target.closest(".kar-gerar")) return;
  const m = karaoke.find((x) => x.slug === linha.dataset.slug);
  let r;
  try {
    r = await fetch("/api/gerar_karaoke", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slug: m.slug }) });
  } catch { aviso("Servidor fora do ar? Não consegui enviar o pedido.", true); return; }
  if (!r.ok) { const d = await r.json().catch(() => ({})); aviso("Não deu para pedir a geração: " + (d.detail || r.status), true); return; }
  aviso(`“${m.titulo}” entrou na fila.`);
  abrirAba("fila");
});

// aba pela URL (#karaoke etc.): no fim, depois de tudo declarado
if (["biblioteca", "fila", "buscar", "karaoke"].includes(location.hash.slice(1))) abrirAba(location.hash.slice(1));
