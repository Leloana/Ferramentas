// --- Estado Global ---
let currentApps = [];
let activeAppId = "tts_platform_pt";
let chatWs = null;
let terminalWs = null;
let currentAssistantMsgElement = null;

// --- Elementos DOM ---
const loginModal = document.getElementById("login-modal");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("password-input");
const loginError = document.getElementById("login-error");
const appContainer = document.getElementById("app-container");

const appSelect = document.getElementById("app-select");
const addCustomAppBtn = document.getElementById("add-custom-app-btn");
const appIframe = document.getElementById("app-iframe");
const previewAppTitle = document.getElementById("preview-app-title");
const previewAppUrl = document.getElementById("preview-app-url");
const reloadPreviewBtn = document.getElementById("reload-preview-btn");
const openExternalBtn = document.getElementById("open-external-btn");

const vramPill = document.getElementById("vram-pill");
const vramText = document.getElementById("vram-text");
const modelPill = document.getElementById("model-pill");
const modelPillText = document.getElementById("model-pill-text");
const logoutBtn = document.getElementById("logout-btn");

const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const sendChatBtn = document.getElementById("send-chat-btn");
const clearChatBtn = document.getElementById("clear-chat-btn");

// Sub-abas do painel direito (MCP vs Terminal)
const tabBtnMcp = document.getElementById("tab-btn-mcp");
const tabBtnTerminal = document.getElementById("tab-btn-terminal");
const mcpContainer = document.getElementById("mcp-container");
const terminalContainer = document.getElementById("terminal-container");

// Alternador dentro da aba MCP (Tools vs Web Preview)
const btnShowMcpTools = document.getElementById("btn-show-mcp-tools");
const btnShowWebPreview = document.getElementById("btn-show-web-preview");
const mcpToolsView = document.getElementById("mcp-tools-view");
const webPreviewView = document.getElementById("web-preview-view");

const mcpToolsList = document.getElementById("mcp-tools-list");
const mcpCallLog = document.getElementById("mcp-call-log");
const clearMcpLogBtn = document.getElementById("clear-mcp-log-btn");

// Terminal dedicado
const quickChipsContainer = document.getElementById("quick-action-chips");
const terminalOutput = document.getElementById("terminal-output");
const terminalForm = document.getElementById("terminal-form");
const terminalInput = document.getElementById("terminal-input");

// Modal de Modelo
const modelModal = document.getElementById("model-modal");
const closeModelModal = document.getElementById("close-model-modal");
const modelForm = document.getElementById("model-form");
const providerSelect = document.getElementById("provider-select");
const modelNameInput = document.getElementById("model-name-input");
const apiKeyInput = document.getElementById("api-key-input");
const baseUrlInput = document.getElementById("base-url-input");

// --- Inicialização ---
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  const authOk = await checkAuth();
  if (authOk) {
    showApp();
  } else {
    showLogin();
  }
});

// --- Autenticação ---
async function checkAuth() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    return data.authenticated;
  } catch {
    return false;
  }
}

function showLogin() {
  loginModal.classList.remove("hidden");
  appContainer.classList.add("hidden");
  passwordInput.focus();
}

function showApp() {
  loginModal.classList.add("hidden");
  appContainer.classList.remove("hidden");
  initApp();
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ password: passwordInput.value })
    });
    const data = await res.json();
    if (data.ok) {
      showApp();
    } else {
      loginError.textContent = data.error || "Senha incorreta.";
      loginError.classList.remove("hidden");
    }
  } catch (err) {
    loginError.textContent = "Erro ao conectar com o servidor.";
    loginError.classList.remove("hidden");
  }
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.reload();
});

// --- Inicialização dos Componentes ---
async function initApp() {
  await loadApps();
  await loadVram();
  await loadModelConfig();
  await loadMcpTools();
  await loadMcpHistory();
  connectChatWs();
  connectTerminalWs();

  // Polling leve para VRAM e histórico MCP a cada 15 segundos
  setInterval(loadVram, 15000);
  setInterval(loadMcpHistory, 10000);
}

// --- Carregar Aplicações & Iframe ---
async function loadApps() {
  try {
    const res = await fetch("/api/apps");
    const data = await res.json();
    currentApps = data.apps || [];
    activeAppId = data.active_app || (currentApps[0] ? currentApps[0].id : "");

    // Preenche Select
    appSelect.innerHTML = "";
    currentApps.forEach(app => {
      const opt = document.createElement("option");
      opt.value = app.id;
      opt.textContent = `${app.name} (porta ${app.port})`;
      if (app.id === activeAppId) opt.selected = true;
      appSelect.appendChild(opt);
    });

    // Renderiza Quick Action Chips do terminal
    renderQuickChips(data.quick_actions || []);

    // Atualiza preview
    updatePreview(activeAppId);
  } catch (err) {
    console.error("Erro ao carregar apps:", err);
  }
}

function updatePreview(appId) {
  activeAppId = appId;
  const app = currentApps.find(a => a.id === appId);
  if (!app) return;

  previewAppTitle.textContent = app.name;
  previewAppUrl.textContent = app.url;

  // Usa o proxy reverso para contornar Mixed Content no HTTPS do Cloudflare Tunnel
  const proxyUrl = `/proxy/${app.id}/`;
  appIframe.src = proxyUrl;
}

appSelect.addEventListener("change", async (e) => {
  const chosen = e.target.value;
  updatePreview(chosen);
  await fetch("/api/apps/active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: jsonStringify({ app_id: chosen })
  });
});

reloadPreviewBtn.addEventListener("click", () => {
  if (appIframe) appIframe.src = appIframe.src;
});

openExternalBtn.addEventListener("click", () => {
  const app = currentApps.find(a => a.id === activeAppId);
  if (app) window.open(app.url, "_blank");
});

addCustomAppBtn.addEventListener("click", async () => {
  const name = prompt("Nome da aplicação (ex: Meu App):");
  if (!name) return;
  const url = prompt("URL da aplicação (ex: http://127.0.0.1:8080):", "http://127.0.0.1:8080");
  if (!url) return;

  let port = 8000;
  try {
    const u = new URL(url);
    port = parseInt(u.port) || 80;
  } catch {}

  const id = name.toLowerCase().replace(/[^a-z0-9]/g, "_") + "_" + Math.floor(Math.random() * 1000);

  const res = await fetch("/api/apps", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: jsonStringify({ id, name, url, port, desc: "Custom" })
  });
  const data = await res.json();
  if (data.ok) {
    await loadApps();
    appSelect.value = id;
    updatePreview(id);
  }
});

// --- Aba MCP: Ferramentas e Histórico ---
async function loadMcpTools() {
  try {
    const res = await fetch("/api/mcp/tools");
    const data = await res.json();
    const tools = data.tools || [];
    renderMcpTools(tools);
  } catch (err) {
    console.error("Erro ao carregar ferramentas MCP:", err);
  }
}

function renderMcpTools(tools) {
  mcpToolsList.innerHTML = "";
  tools.forEach(t => {
    const card = document.createElement("div");
    card.className = "tool-card";

    const title = document.createElement("div");
    title.className = "tool-card-title";
    title.textContent = `🛠️ ${t.name}`;

    const desc = document.createElement("div");
    desc.className = "tool-card-desc";
    desc.textContent = t.description;

    const runBtn = document.createElement("button");
    runBtn.className = "btn-tool-run";
    runBtn.textContent = "Executar";
    runBtn.addEventListener("click", () => triggerMcpTool(t));

    card.appendChild(title);
    card.appendChild(desc);
    card.appendChild(runBtn);
    mcpToolsList.appendChild(card);
  });
}

async function triggerMcpTool(tool) {
  let args = {};
  const schema = tool.inputSchema || {};
  const required = schema.required || [];

  if (tool.name === "execute_whitelisted_command") {
    const cmd = prompt("Digite o comando a executar (ex: git status, nvidia-smi):", "git status");
    if (!cmd) return;
    args = { command: cmd };
  } else if (tool.name === "set_active_application") {
    const appId = prompt(`Digite o ID da aplicação (ex: ${currentApps.map(a => a.id).join(", ")}):`, activeAppId);
    if (!appId) return;
    args = { app_id: appId };
  } else if (tool.name === "send_remote_chat") {
    const msg = prompt("Digite a mensagem a enviar para a tela remota:");
    if (!msg) return;
    args = { message: msg };
  }

  try {
    const res = await fetch("/api/mcp/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonStringify({ name: tool.name, arguments: args })
    });
    const data = await res.json();
    renderMcpLogs(data.history || []);

    if (tool.name === "set_active_application" && args.app_id) {
      updatePreview(args.app_id);
      appSelect.value = args.app_id;
    }
  } catch (err) {
    alert("Erro ao executar ferramenta MCP: " + err);
  }
}

async function loadMcpHistory() {
  try {
    const res = await fetch("/api/mcp/history");
    const data = await res.json();
    renderMcpLogs(data.history || []);
  } catch {}
}

function renderMcpLogs(history) {
  if (!history || history.length === 0) {
    mcpCallLog.innerHTML = `<div class="mcp-log-empty">Nenhuma chamada de ferramenta registrada ainda.</div>`;
    return;
  }

  mcpCallLog.innerHTML = "";
  // Exibe do mais recente para o mais antigo
  history.slice().reverse().forEach(item => {
    const row = document.createElement("div");
    row.className = "mcp-log-item";

    const header = document.createElement("div");
    header.className = "mcp-log-header";
    header.innerHTML = `<span>[${item.timestamp}]</span> <strong>${item.name}</strong>`;

    const resPre = document.createElement("pre");
    resPre.className = "mcp-log-result";
    resPre.textContent = item.result || "(sem retorno)";

    row.appendChild(header);
    row.appendChild(resPre);
    mcpCallLog.appendChild(row);
  });
}

clearMcpLogBtn.addEventListener("click", () => {
  mcpCallLog.innerHTML = `<div class="mcp-log-empty">Log limpo.</div>`;
});

// --- Alternadores de Visão (MCP Tools vs Web Preview) ---
btnShowMcpTools.addEventListener("click", () => {
  btnShowMcpTools.classList.add("active");
  btnShowWebPreview.classList.remove("active");
  mcpToolsView.classList.remove("hidden");
  webPreviewView.classList.add("hidden");
});

btnShowWebPreview.addEventListener("click", () => {
  btnShowWebPreview.classList.add("active");
  btnShowMcpTools.classList.remove("active");
  webPreviewView.classList.remove("hidden");
  mcpToolsView.classList.add("hidden");
});

// --- Alternadores de Aba no Painel Direito (Desktop) ---
tabBtnMcp.addEventListener("click", () => {
  tabBtnMcp.classList.add("active");
  tabBtnTerminal.classList.remove("active");
  mcpContainer.classList.remove("hidden");
  terminalContainer.classList.add("hidden");
});

tabBtnTerminal.addEventListener("click", () => {
  tabBtnTerminal.classList.add("active");
  tabBtnMcp.classList.remove("active");
  terminalContainer.classList.remove("hidden");
  mcpContainer.classList.add("hidden");
  terminalInput.focus();
});

// --- Telemetria VRAM ---
async function loadVram() {
  try {
    const res = await fetch("/api/vram");
    const data = await res.json();
    if (data.available) {
      vramText.textContent = `VRAM: ${data.used_gb} / ${data.total_gb} GB (${data.percent}%)`;
    } else {
      vramText.textContent = "GPU: Local";
    }
  } catch {
    vramText.textContent = "GPU: --";
  }
}

vramPill.addEventListener("click", loadVram);

// --- Configuração do Modelo LLM ---
async function loadModelConfig() {
  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    const curr = data.current || {};
    modelPillText.textContent = `IA: ${curr.provider || "ollama"} (${curr.model || "default"})`;
    providerSelect.value = curr.provider || "ollama";
    modelNameInput.value = curr.model || "";
    apiKeyInput.value = curr.api_key || "";
    baseUrlInput.value = curr.base_url || "";
  } catch (err) {
    console.error("Erro ao carregar modelos:", err);
  }
}

modelPill.addEventListener("click", () => modelModal.classList.remove("hidden"));
closeModelModal.addEventListener("click", () => modelModal.classList.add("hidden"));

modelForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    provider: providerSelect.value,
    model: modelNameInput.value.trim(),
    api_key: apiKeyInput.value.trim(),
    base_url: baseUrlInput.value.trim()
  };
  await fetch("/api/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: jsonStringify(payload)
  });
  modelModal.classList.add("hidden");
  await loadModelConfig();
});

// --- WebSocket do Chat ---
function connectChatWs() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  chatWs = new WebSocket(`${protocol}//${window.location.host}/ws/chat`);

  chatWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "start") {
      currentAssistantMsgElement = appendMessage("assistant", "");
    } else if (data.type === "chunk") {
      if (currentAssistantMsgElement) {
        currentAssistantMsgElement.innerHTML += formatText(data.content);
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }
    } else if (data.type === "done") {
      currentAssistantMsgElement = null;
    } else if (data.type === "error") {
      appendMessage("system-msg", `❌ ${data.content}`);
      currentAssistantMsgElement = null;
    }
  };

  chatWs.onclose = () => {
    setTimeout(connectChatWs, 3000);
  };
}

function sendChatMessage() {
  const text = chatInput.value.trim();
  if (!text || !chatWs || chatWs.readyState !== WebSocket.OPEN) return;

  appendMessage("user", text);
  chatInput.value = "";
  chatInput.style.height = "auto";

  chatWs.send(jsonStringify({ message: text }));
}

function appendMessage(role, content) {
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${role}`;
  msgDiv.innerHTML = formatText(content);
  chatMessages.appendChild(msgDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msgDiv;
}

clearChatBtn.addEventListener("click", () => {
  chatMessages.innerHTML = `
    <div class="message system-msg">
      👋 Conversa limpa. Você pode enviar uma nova pergunta ou comando.
    </div>
  `;
});

// --- WebSocket do Terminal Dedicado ---
function connectTerminalWs() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  terminalWs = new WebSocket(`${protocol}//${window.location.host}/ws/terminal`);

  terminalWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "output") {
      terminalOutput.textContent += data.text;
      terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }
  };

  terminalWs.onclose = () => {
    setTimeout(connectTerminalWs, 3000);
  };
}

function sendTerminalCommand(cmd) {
  const command = (cmd || terminalInput.value).trim();
  if (!command || !terminalWs || terminalWs.readyState !== WebSocket.OPEN) return;

  terminalInput.value = "";
  terminalWs.send(jsonStringify({ command }));
}

terminalForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendTerminalCommand();
});

function renderQuickChips(chips) {
  quickChipsContainer.innerHTML = "";
  chips.forEach(c => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.textContent = c.label;
    btn.title = `$ ${c.cmd}`;
    btn.addEventListener("click", () => {
      // Se não estiver na aba do terminal, troca pra ela
      tabBtnTerminal.click();
      sendTerminalCommand(c.cmd);
    });
    quickChipsContainer.appendChild(btn);
  });
}

// --- Navegação Mobile (Tabs) ---
function setupEventListeners() {
  const tabButtons = document.querySelectorAll(".mobile-nav .tab-btn");
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      tabButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const targetId = btn.getAttribute("data-target");
      const chatPane = document.getElementById("chat-pane");
      const rightPane = document.getElementById("right-pane");

      if (targetId === "chat-pane") {
        chatPane.classList.add("active-pane");
        rightPane.classList.remove("active-pane");
      } else if (targetId === "mcp-container") {
        chatPane.classList.remove("active-pane");
        rightPane.classList.add("active-pane");
        tabBtnMcp.click();
      } else if (targetId === "terminal-container") {
        chatPane.classList.remove("active-pane");
        rightPane.classList.add("active-pane");
        tabBtnTerminal.click();
      }
    });
  });

  // Envio de chat por Enter (Shift+Enter para pular linha)
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  sendChatBtn.addEventListener("click", sendChatMessage);
}

// --- Funções Utilitárias ---
function jsonStringify(obj) {
  return JSON.stringify(obj);
}

function formatText(str) {
  if (!str) return "";
  let escaped = str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  return escaped;
}
