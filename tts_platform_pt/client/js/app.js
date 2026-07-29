const textoEl = document.getElementById("texto");
const vozEl = document.getElementById("voz");
const uploadVozEl = document.getElementById("upload-voz");
const normalizarEl = document.getElementById("normalizar");
const gerarBtn = document.getElementById("gerar");
const statusEl = document.getElementById("status");
const spinnerEl = document.getElementById("spinner");
const resultadoEl = document.getElementById("resultado");
const playerEl = document.getElementById("player");
const baixarEl = document.getElementById("baixar");
const textoUsadoEl = document.getElementById("texto-usado");
const contadorEl = document.getElementById("contador-tokens");
const avisoNormalizacaoEl = document.getElementById("aviso-normalizacao");

// Overhead aproximado do template de instruções enviado ao Ollama junto do
// texto (ver prompt em server/engine/text_preprocessor.py).
const PROMPT_OVERHEAD_TOKENS = 200;

let ollamaNumCtx = null;

function definirCarregando(carregando, mensagem) {
  spinnerEl.hidden = !carregando;
  if (mensagem !== undefined) statusEl.textContent = mensagem;
}

// Estimativa grosseira (~4 caracteres por token) só para dar uma noção de
// espaço; o Ollama só entra em jogo se "normalizar" estiver marcado.
function atualizarContadorTokens() {
  if (!normalizarEl.checked || !ollamaNumCtx) {
    contadorEl.hidden = true;
    return;
  }

  const texto = textoEl.value;
  if (!texto.trim()) {
    contadorEl.hidden = true;
    return;
  }

  const tokensEstimados = PROMPT_OVERHEAD_TOKENS + Math.ceil(texto.length / 4);
  const percentual = tokensEstimados / ollamaNumCtx;

  contadorEl.hidden = false;
  contadorEl.textContent =
    `≈${tokensEstimados} tokens de ${ollamaNumCtx} do contexto do Ollama (${Math.round(percentual * 100)}%)`;
  contadorEl.classList.toggle("estourado", percentual >= 1);
  contadorEl.classList.toggle("atencao", percentual >= 0.75 && percentual < 1);
}

textoEl.addEventListener("input", atualizarContadorTokens);
normalizarEl.addEventListener("change", atualizarContadorTokens);

async function carregarVozes() {
  vozEl.disabled = true;
  uploadVozEl.disabled = true;
  gerarBtn.disabled = true;
  definirCarregando(
    true,
    "Carregando vozes... (na primeira vez, baixa o modelo XTTS-v2 do Hugging Face, ~1.8GB — pode levar alguns minutos)"
  );

  try {
    const resp = await fetch("/api/voices");
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Falha ao carregar vozes.");

    vozEl.innerHTML = "";
    for (const nome of data.embutidas) {
      const opt = document.createElement("option");
      opt.value = nome;
      opt.textContent = `🔊 ${nome}`;
      vozEl.appendChild(opt);
    }
    for (const arquivo of data.personalizadas) {
      const opt = document.createElement("option");
      opt.value = `custom:${arquivo}`;
      opt.textContent = `🎙️ ${arquivo} (clonada)`;
      vozEl.appendChild(opt);
    }

    ollamaNumCtx = data.ollama_num_ctx || null;
    atualizarContadorTokens();

    vozEl.disabled = false;
    uploadVozEl.disabled = false;
    gerarBtn.disabled = false;
    definirCarregando(false, "Pronto.");
  } catch (e) {
    definirCarregando(false, `Erro ao carregar vozes: ${e.message} — recarregue a página para tentar novamente.`);
    throw e;
  }
}

uploadVozEl.addEventListener("change", async () => {
  const arquivo = uploadVozEl.files[0];
  if (!arquivo) return;

  gerarBtn.disabled = true;
  uploadVozEl.disabled = true;
  definirCarregando(true, "Enviando amostra de voz...");
  const form = new FormData();
  form.append("file", arquivo);

  try {
    const resp = await fetch("/api/voices", { method: "POST", body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Falha no upload.");
    await carregarVozes();
    vozEl.value = `custom:${data.nome}`;
    definirCarregando(false, "Voz clonada adicionada à lista.");
  } catch (e) {
    definirCarregando(false, `Erro: ${e.message}`);
  } finally {
    uploadVozEl.value = "";
    uploadVozEl.disabled = false;
    gerarBtn.disabled = false;
  }
});

gerarBtn.addEventListener("click", async () => {
  const texto = textoEl.value.trim();
  if (!texto) {
    statusEl.textContent = "Digite um texto primeiro.";
    return;
  }

  gerarBtn.disabled = true;
  definirCarregando(true, "Gerando áudio (pode levar alguns segundos)...");
  resultadoEl.hidden = true;

  try {
    const resp = await fetch("/api/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        texto,
        voice_id: vozEl.value || null,
        normalizar: normalizarEl.checked,
      }),
    });

    if (!resp.ok) {
      const erro = await resp.json();
      throw new Error(erro.detail || "Falha ao gerar áudio.");
    }

    const data = await resp.json();
    playerEl.src = data.audio_url;
    baixarEl.href = data.audio_url;
    textoUsadoEl.textContent = data.texto_usado;
    if (data.aviso_normalizacao) {
      avisoNormalizacaoEl.textContent = `⚠️ ${data.aviso_normalizacao}`;
      avisoNormalizacaoEl.hidden = false;
    } else {
      avisoNormalizacaoEl.hidden = true;
    }
    resultadoEl.hidden = false;
    definirCarregando(false, "Pronto.");
    playerEl.play().catch(() => {});
  } catch (e) {
    definirCarregando(false, `Erro: ${e.message}`);
  } finally {
    gerarBtn.disabled = false;
  }
});

carregarVozes().catch((e) => {
  console.error(e);
});
