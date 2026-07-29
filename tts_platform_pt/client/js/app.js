const textoEl = document.getElementById("texto");
const vozEl = document.getElementById("voz");
const uploadVozEl = document.getElementById("upload-voz");
const normalizarEl = document.getElementById("normalizar");
const gerarBtn = document.getElementById("gerar");
const statusEl = document.getElementById("status");
const resultadoEl = document.getElementById("resultado");
const playerEl = document.getElementById("player");
const baixarEl = document.getElementById("baixar");
const textoUsadoEl = document.getElementById("texto-usado");

async function carregarVozes() {
  const resp = await fetch("/api/voices");
  const data = await resp.json();

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
}

uploadVozEl.addEventListener("change", async () => {
  const arquivo = uploadVozEl.files[0];
  if (!arquivo) return;

  statusEl.textContent = "Enviando amostra de voz...";
  const form = new FormData();
  form.append("file", arquivo);

  try {
    const resp = await fetch("/api/voices", { method: "POST", body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Falha no upload.");
    await carregarVozes();
    vozEl.value = `custom:${data.nome}`;
    statusEl.textContent = "Voz clonada adicionada à lista.";
  } catch (e) {
    statusEl.textContent = `Erro: ${e.message}`;
  } finally {
    uploadVozEl.value = "";
  }
});

gerarBtn.addEventListener("click", async () => {
  const texto = textoEl.value.trim();
  if (!texto) {
    statusEl.textContent = "Digite um texto primeiro.";
    return;
  }

  gerarBtn.disabled = true;
  statusEl.textContent = "Gerando áudio (pode levar alguns segundos)...";
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
    resultadoEl.hidden = false;
    statusEl.textContent = "Pronto.";
    playerEl.play().catch(() => {});
  } catch (e) {
    statusEl.textContent = `Erro: ${e.message}`;
  } finally {
    gerarBtn.disabled = false;
  }
});

carregarVozes().catch((e) => {
  statusEl.textContent = `Erro ao carregar vozes: ${e.message}`;
});
