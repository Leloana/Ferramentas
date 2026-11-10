// Partitura — front-end (vanilla JS)
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const NIVEL_NOME = { facil: "Fácil", medio: "Médio", dificil: "Difícil" };
// versão recomendada por nível (analisar.py: tocabilidade + coerência com a harmonia, 7 músicas)
const PADRAO = { facil: "Acordes", medio: "HibridoAMT", dificil: "AMT-APC" };
const VERSAO_NOME = { HibridoAMT: "Híbrido (AMT)", Hibrido: "Híbrido (Pop2Piano)", Acordes: "Acordes", Pop2Piano: "Pop2Piano", "AMT-APC": "AMT-APC" };
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const urlArq = (rel) => "/arquivos/" + rel.split("/").map(encodeURIComponent).join("/");
const dur = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "");

let musicas = [];
let selecionada = null;
let escolha = { nivel: "medio", versao: "HibridoAMT" };
try { escolha = { ...escolha, ...JSON.parse(localStorage.getItem("partitura.escolha") || "{}") }; } catch {}

// ------------------------------------------------------------------ abas
function abrirAba(nome) {
  $$(".aba").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
  $$(".painel").forEach((p) => p.classList.toggle("ativo", p.id === nome));
  if (nome === "biblioteca") carregarMusicas();
  if (nome === "fila") carregarJobs();
}
$$(".aba").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.aba)));

// ------------------------------------------------------------------ busca
const player = $("#player");
let tocandoId = null;

$("#formBusca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (q.length < 2) return;
  $("#statusBusca").textContent = "Buscando…";
  $("#resultados").innerHTML = "";
  try {
    const r = await fetch(`/api/busca?q=${encodeURIComponent(q)}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "erro");
    $("#statusBusca").textContent = d.resultados.length ? "" : "Nada encontrado.";
    const jaTem = new Set(musicas.map((m) => m.video_id).filter(Boolean));
    $("#resultados").innerHTML = d.resultados.map((v) => `
      <article class="res" data-id="${v.id}">
        <div class="capa">
          <img src="${v.thumb}" alt="" loading="lazy">
          <button class="tocar" title="Ouvir antes">▶</button>
          <span class="dur">${dur(v.duracao)}</span>
        </div>
        <div class="info">
          <h3>${esc(v.titulo_video)}</h3>
          <span class="canal">${esc(v.canal)}</span>
          ${jaTem.has(v.id) ? '<span class="ja">✓ já está na biblioteca</span>' : ""}
          <button class="btn primario gerar">Gerar partitura</button>
        </div>
      </article>`).join("");
    $$(".res").forEach((el, i) => {
      const v = d.resultados[i];
      $(".tocar", el).addEventListener("click", () => tocar(v.id, $(".tocar", el)));
      $(".gerar", el).addEventListener("click", () => abrirDialogo(v));
    });
  } catch (err) {
    $("#statusBusca").textContent = "Erro na busca: " + err.message;
  }
});

function tocar(id, botao) {
  $$(".tocar").forEach((b) => { b.textContent = "▶"; b.classList.remove("carregando"); });
  if (tocandoId === id && !player.paused) { player.pause(); tocandoId = null; return; }
  tocandoId = id;
  botao.classList.add("carregando");
  botao.textContent = "…";
  player.src = `/api/previa/${id}`;
  player.play().then(() => { botao.classList.remove("carregando"); botao.textContent = "❚❚"; })
    .catch(() => { botao.classList.remove("carregando"); botao.textContent = "!"; });
}
player.addEventListener("ended", () => $$(".tocar").forEach((b) => (b.textContent = "▶")));

// ------------------------------------------------------------------ diálogo de geração
let videoAtual = null;
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
  try { await enviarPedido(); } finally { botao.disabled = false; botao.textContent = "Gerar partitura"; }
});
async function enviarPedido() {
  const niveis = $$('input[name="nivel"]:checked').map((i) => i.value);
  const versoes = $$('input[name="versao"]:checked').map((i) => i.value);
  const corpo = {
    video_id: videoAtual.id, titulo: $("#gTitulo").value.trim(), artista: $("#gArtista").value.trim(),
    niveis: niveis.length ? niveis : ["medio"], versoes: versoes.length ? versoes : ["Hibrido"],
    idioma: $("#gIdioma").value,
  };
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
async function carregarJobs() {
  const d = await (await fetch("/api/jobs")).json();
  const ativos = d.jobs.filter((j) => j.status === "fila" || j.status === "rodando").length;
  $("#contFila").textContent = ativos ? `(${ativos})` : "";
  $("#listaJobs").innerHTML = d.jobs.length ? d.jobs.map((j) => `
    <div class="job ${j.status}">
      <div class="cab">
        <h3>${esc(j.titulo)} <small class="etapa">${esc(j.artista)}</small></h3>
        <span class="etapa">${j.niveis.map((n) => NIVEL_NOME[n]).join(", ")} · ${j.versoes.map((v) => VERSAO_NOME[v]).join(", ")}</span>
      </div>
      <div class="barra"><div style="width:${j.progresso}%"></div></div>
      <div class="cab">
        <span class="etapa">${j.status === "pronto" ? "✓ Pronto" : j.status === "erro" ? "✗ " + esc(j.etapa) : esc(j.etapa)}${j.status === "rodando" ? ` · ${j.progresso}%` : ""}</span>
        ${j.status === "pronto" ? `<button class="btn pequeno" data-abrir="${esc(j.pasta)}">Abrir partitura</button>` : ""}
      </div>
      ${j.log.length ? `<details><summary class="etapa">detalhes</summary><pre>${esc(j.log.join("\n"))}</pre></details>` : ""}
    </div>`).join("") : '<p class="vazio-msg">Nenhum pedido ainda. Busque uma música e clique em “Gerar partitura”.</p>';
  $$("[data-abrir]").forEach((b) => b.addEventListener("click", async () => {
    abrirAba("biblioteca");
    await carregarMusicas();
    selecionar(b.dataset.abrir);
  }));
  clearTimeout(timerFila);
  if (ativos) timerFila = setTimeout(() => { carregarJobs(); if ($("#biblioteca").classList.contains("ativo")) carregarMusicas(); }, 2000);
}

// ------------------------------------------------------------------ biblioteca
async function carregarMusicas() {
  const d = await (await fetch("/api/musicas")).json();
  musicas = d.musicas;
  $("#contBib").textContent = musicas.length ? `(${musicas.length})` : "";
  $("#listaMusicas").innerHTML = musicas.map((m) => `
    <button class="mus ${selecionada === m.pasta ? "ativa" : ""}" data-pasta="${esc(m.pasta)}">
      ${m.video_id ? `<img src="https://i.ytimg.com/vi/${m.video_id}/mqdefault.jpg" alt="">` : '<img alt="">'}
      <span><b>${esc(m.titulo)}</b><small>${esc(m.artista)}</small></span>
    </button>`).join("") || '<p class="vazio-msg">Nenhuma partitura ainda.</p>';
  $$(".mus").forEach((b) => b.addEventListener("click", () => selecionar(b.dataset.pasta)));
  if (!selecionada && musicas.length) selecionar(musicas[0].pasta);
}

function selecionar(pasta) {
  selecionada = pasta;
  $$(".mus").forEach((b) => b.classList.toggle("ativa", b.dataset.pasta === pasta));
  desenharVisor();
}

function desenharVisor() {
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
    <h2>${esc(m.titulo)}</h2>
    <p class="art">${esc(m.artista)}</p>
    <div class="seletor">
      <div class="grupo">${["facil", "medio", "dificil"].map((n) => `<button data-nivel="${n}" class="${n === escolha.nivel ? "ativa" : ""}" ${m.arquivos[n] ? "" : "disabled"}>${NIVEL_NOME[n]}</button>`).join("")}</div>
      <div class="grupo">${["HibridoAMT", "Hibrido", "Acordes", "Pop2Piano", "AMT-APC"].map((v) => `<button data-versao="${v}" class="${v === escolha.versao ? "ativa" : ""}" ${m.arquivos[escolha.nivel][v] ? "" : "disabled"} title="${PADRAO[escolha.nivel] === v ? "recomendada para este nível" : ""}">${VERSAO_NOME[v]}${PADRAO[escolha.nivel] === v ? " ★" : ""}</button>`).join("")}</div>
    </div>
    <div class="audios">
      ${item.previa ? `<div><label>🎹 Como soa esta partitura (piano)</label><audio controls preload="none" src="${urlArq(item.previa)}"></audio></div>` : ""}
      ${m.original ? `<div><label>🎧 Gravação original</label><audio controls preload="none" src="${urlArq(m.original)}"></audio></div>` : ""}
    </div>
    ${item.pdf ? `<iframe class="pdf" src="${urlArq(item.pdf)}#view=FitH"></iframe>` : "<p>Sem PDF para esta combinação.</p>"}
    <div class="links">
      ${item.pdf ? `<a href="${urlArq(item.pdf)}" target="_blank">abrir PDF em nova aba</a>` : ""}
      ${m.editaveis.filter((e) => e.includes(`${escolha.versao} - ${{ facil: "Facil", medio: "Medio", dificil: "Dificil" }[escolha.nivel]}`))
        .map((e) => `<a href="${urlArq(e)}" download>baixar MusicXML (MuseScore)</a>`).join("")}
    </div>`;
  $$("[data-nivel]", visor).forEach((b) => b.addEventListener("click", () => {
    escolha.nivel = b.dataset.nivel;
    // ao trocar de nível, vai pra versão recomendada dele (análise de 7 músicas, ver README)
    if (m.arquivos[escolha.nivel]?.[PADRAO[escolha.nivel]]) escolha.versao = PADRAO[escolha.nivel];
    desenharVisor();
  }));
  $$("[data-versao]", visor).forEach((b) => b.addEventListener("click", () => { escolha.versao = b.dataset.versao; desenharVisor(); }));
}

carregarMusicas();
carregarJobs();
if (["biblioteca", "fila", "buscar"].includes(location.hash.slice(1))) abrirAba(location.hash.slice(1));
