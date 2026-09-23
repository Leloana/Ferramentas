// --- Estado Global ---
let ptyWs = null;
let eventsWs = null;
let chatWs = null;
let term = null;
let fitAddon = null;
let activeTab = "tab-terminal";
let activePreview = { url: "http://127.0.0.1:8000", title: "Aplicação", app_id: "tts_platform_pt" };
let currentClientIp = "";

// --- Elementos do DOM ---
const loginModal = document.getElementById("login-modal");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("password-input");
const loginError = document.getElementById("login-error");
const appContainer = document.getElementById("app-container");
const logoutBtn = document.getElementById("logout-btn");
const connStatusDot = document.getElementById("conn-status-dot");
const vramBadge = document.getElementById("vram-badge");
const vramText = document.getElementById("vram-text");

// Toast
const toastNotification = document.getElementById("toast-notification");
const toastTitle = document.getElementById("toast-title");
const toastBody = document.getElementById("toast-body");
const toastActionBtn = document.getElementById("toast-action-btn");

// Preview
const previewTitle = document.getElementById("preview-title");
const previewUrlBadge = document.getElementById("preview-url-badge");
const previewIframe = document.getElementById("preview-iframe");
const btnToggleCustomUrl = document.getElementById("btn-toggle-custom-url");
const customUrlBar = document.getElementById("custom-url-bar");
const customUrlInput = document.getElementById("custom-url-input");
const btnApplyCustomUrl = document.getElementById("btn-apply-custom-url");
const btnReloadPreview = document.getElementById("btn-reload-preview");
const btnOpenExternal = document.getElementById("btn-open-external");
const appBadgeDots = [document.getElementById("app-badge-dot"), document.getElementById("mobile-app-badge")];

// Status & Whitelist
const statusTunnelUrl = document.getElementById("status-tunnel-url");
const btnCopyTunnel = document.getElementById("btn-copy-tunnel");
const currentClientIpEl = document.getElementById("current-client-ip");
const whitelistToggle = document.getElementById("whitelist-toggle");
const btnWhitelistCurrentIp = document.getElementById("btn-whitelist-current-ip");
const whitelistItems = document.getElementById("whitelist-items");
const manualIpInput = document.getElementById("manual-ip-input");
const btnAddManualIp = document.getElementById("btn-add-manual-ip");
const btnRefreshVram = document.getElementById("btn-refresh-vram");
const metricVramUsage = document.getElementById("metric-vram-usage");
const metricVramBar = document.getElementById("metric-vram-bar");
const metricGpuTemp = document.getElementById("metric-gpu-temp");
const metricGpuUtil = document.getElementById("metric-gpu-util");

// Terminal
const xtermContainer = document.getElementById("xterm-container");
const terminalStatusText = document.getElementById("terminal-status-text");
const btnRestartPty = document.getElementById("btn-restart-pty");
const btnClearTerm = document.getElementById("btn-clear-term");

// Chat
const chatMessagesContainer = document.getElementById("chat-messages-container");
const webChatInput = document.getElementById("web-chat-input");
const btnSendWebChat = document.getElementById("btn-send-web-chat");
const btnClearChat = document.getElementById("btn-clear-chat");

// --- Inicialização ---
document.addEventListener("DOMContentLoaded", async () => {
  setupNavigation();
  setupTouchBar();
  setupPreviewControls();
  setupWhitelistControls();
  setupChatControls();

  const authenticated = await checkAuth();
  if (authenticated) {
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
  initApplication();
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.classList.add("hidden");
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: passwordInput.value })
    });
    const data = await res.json();
    if (data.ok) {
      showApp();
    } else {
      loginError.textContent = data.error || "Senha incorreta.";
      loginError.classList.remove("hidden");
    }
  } catch {
    loginError.textContent = "Erro ao conectar com o servidor.";
    loginError.classList.remove("hidden");
  }
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.reload();
});

// --- Inicialização do App ---
async function initApplication() {
  initTerminal();
  connectPtyWs();
  connectEventsWs();
  connectChatWs();
  await loadPreviewState();
  await loadIpStatus();
  await loadVramTelemetry();
  await loadTunnelInfo();

  // Polling periódico de telemetria
  setInterval(loadVramTelemetry, 15000);
}

// --- Navegação entre Abas (Fazer uma coisa por vez) ---
function setupNavigation() {
  const allTabButtons = document.querySelectorAll("[data-tab]");
  allTabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      switchTab(targetTab);
    });
  });

  toastActionBtn.addEventListener("click", () => {
    toastNotification.classList.add("hidden");
    switchTab("tab-app");
  });
}

function switchTab(tabId) {
  activeTab = tabId;

  // Atualiza botões
  document.querySelectorAll("[data-tab]").forEach(btn => {
    if (btn.getAttribute("data-tab") === tabId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Alterna views
  document.querySelectorAll(".tab-view").forEach(view => {
    if (view.id === tabId) {
      view.classList.add("active");
    } else {
      view.classList.remove("active");
    }
  });

  // Ajustes específicos ao entrar na aba
  if (tabId === "tab-terminal") {
    setTimeout(() => {
      if (fitAddon) {
        fitAddon.fit();
      }
      if (term) {
        term.focus();
      }
    }, 50);
  } else if (tabId === "tab-app") {
    // Remove badge de notificação
    appBadgeDots.forEach(dot => dot && dot.classList.add("hidden"));
  }
}

// --- Terminal Interativo (xterm.js + PTY) ---
function initTerminal() {
  if (term) return;

  const TerminalConstructor = window.Terminal || Terminal;
  const FitAddonConstructor = (window.FitAddon && window.FitAddon.FitAddon) || window.FitAddon || FitAddon;

  term = new TerminalConstructor({
    cursorBlink: true,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
    fontSize: 13,
    theme: {
      background: "#000000",
      foreground: "#f8fafc",
      cursor: "#38bdf8",
      black: "#0f172a",
      red: "#ef4444",
      green: "#10b981",
      yellow: "#f59e0b",
      blue: "#38bdf8",
      magenta: "#c084fc",
      cyan: "#22d3ee",
      white: "#f8fafc",
      brightBlack: "#475569",
      brightRed: "#f87171",
      brightGreen: "#34d399",
      brightYellow: "#fbbf24",
      brightBlue: "#60a5fa",
      brightMagenta: "#e879f9",
      brightCyan: "#67e8f9",
      brightWhite: "#ffffff"
    },
    convertEol: true,
    scrollback: 5000
  });

  if (FitAddonConstructor) {
    fitAddon = new FitAddonConstructor();
    term.loadAddon(fitAddon);
  }

  term.open(xtermContainer);

  if (fitAddon) {
    setTimeout(() => fitAddon.fit(), 100);
  }

  // Envia digitação direta do teclado para o WebSocket PTY
  term.onData(data => {
    if (ptyWs && ptyWs.readyState === WebSocket.OPEN) {
      ptyWs.send(data);
    }
  });

  // Notifica o backend sobre redimensionamento da janela do terminal
  term.onResize(size => {
    if (ptyWs && ptyWs.readyState === WebSocket.OPEN) {
      ptyWs.send(JSON.stringify({ type: "resize", cols: size.cols, rows: size.rows }));
    }
  });

  window.addEventListener("resize", () => {
    if (activeTab === "tab-terminal" && fitAddon) {
      fitAddon.fit();
    }
  });
}

function connectPtyWs() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ptyWs = new WebSocket(`${protocol}//${window.location.host}/ws/pty?session_id=mobile`);

  ptyWs.onopen = () => {
    terminalStatusText.textContent = "🟢 Conectado ao Bash do host";
    terminalStatusText.style.color = "var(--green)";
    if (fitAddon && term) {
      fitAddon.fit();
      ptyWs.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    }
  };

  ptyWs.onmessage = (event) => {
    if (term) {
      term.write(event.data);
    }
  };

  ptyWs.onclose = () => {
    terminalStatusText.textContent = "🔴 Desconectado (reconectando...)";
    terminalStatusText.style.color = "var(--red)";
    setTimeout(connectPtyWs, 3000);
  };
}

// Botões Touch de Celular para Terminal
function setupTouchBar() {
  // Teclas especiais
  const keyMap = {
    tab: "\t",
    ctrl_c: "\x03",
    esc: "\x1b",
    up: "\x1b[A",
    down: "\x1b[B",
    left: "\x1b[D",
    right: "\x1b[C",
    enter: "\r"
  };

  document.querySelectorAll(".key-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const keyId = btn.getAttribute("data-key");
      const seq = keyMap[keyId];
      if (seq && ptyWs && ptyWs.readyState === WebSocket.OPEN) {
        ptyWs.send(seq);
        if (term) term.focus();
      }
    });
  });

  // Chips de comandos
  document.querySelectorAll(".chip-btn").forEach(chip => {
    chip.addEventListener("click", (e) => {
      e.preventDefault();
      const cmd = chip.getAttribute("data-cmd");
      if (cmd && ptyWs && ptyWs.readyState === WebSocket.OPEN) {
        ptyWs.send(cmd + "\r");
        if (term) term.focus();
      }
    });
  });

  btnRestartPty.addEventListener("click", () => {
    if (ptyWs && ptyWs.readyState === WebSocket.OPEN) {
      ptyWs.send("\x03"); // Envia Ctrl+C primeiro
      ptyWs.send("reset\r");
    }
  });

  btnClearTerm.addEventListener("click", () => {
    if (term) term.clear();
  });
}

// --- Live Preview da Aplicação ---
function computePreviewUrl(targetUrl) {
  if (!targetUrl) return "about:blank";

  // Se a página estiver rodando em HTTPS (Cloudflare Tunnel), direciona portas locais pelo proxy reverso do host
  const isHttps = window.location.protocol === "https:";
  const portMatch = targetUrl.match(/(?:localhost|127\.0\.0\.1):(\d+)/);

  if (isHttps && portMatch) {
    const port = portMatch[1];
    return `/proxy/port/${port}/`;
  }

  return targetUrl;
}

function updatePreviewUi(url, title) {
  activePreview.url = url;
  activePreview.title = title || "Aplicação";

  previewTitle.textContent = activePreview.title;
  previewUrlBadge.textContent = url;
  previewUrlBadge.title = url;

  const resolvedUrl = computePreviewUrl(url);
  if (previewIframe.src !== resolvedUrl) {
    previewIframe.src = resolvedUrl;
  }
}

async function loadPreviewState() {
  try {
    const res = await fetch("/api/preview");
    const data = await res.json();
    if (data.url) {
      updatePreviewUi(data.url, data.title);
    }
  } catch {}
}

function setupPreviewControls() {
  btnToggleCustomUrl.addEventListener("click", () => {
    customUrlBar.classList.toggle("hidden");
    if (!customUrlBar.classList.contains("hidden")) {
      customUrlInput.value = activePreview.url;
      customUrlInput.focus();
    }
  });

  btnApplyCustomUrl.addEventListener("click", async () => {
    const rawVal = customUrlInput.value.trim();
    if (!rawVal) return;

    try {
      const res = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: rawVal, title: "Aplicação Customizada" })
      });
      const data = await res.json();
      if (data.ok) {
        updatePreviewUi(data.preview.url, data.preview.title);
        customUrlBar.classList.add("hidden");
      }
    } catch {}
  });

  btnReloadPreview.addEventListener("click", () => {
    if (previewIframe.src && previewIframe.src !== "about:blank") {
      previewIframe.src = previewIframe.src;
    }
  });

  btnOpenExternal.addEventListener("click", () => {
    if (activePreview.url) {
      const resolved = computePreviewUrl(activePreview.url);
      window.open(resolved, "_blank");
    }
  });
}

// --- Canal de Eventos em Tempo Real (/ws/events) ---
function connectEventsWs() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  eventsWs = new WebSocket(`${protocol}//${window.location.host}/ws/events`);

  eventsWs.onopen = () => {
    connStatusDot.className = "status-indicator online";
  };

  eventsWs.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "preview_updated") {
        updatePreviewUi(data.url, data.title);

        // Se o usuário estiver em outra aba (ex: no terminal digitando prompts), exibe o toast e badge
        if (activeTab !== "tab-app") {
          appBadgeDots.forEach(dot => dot && dot.classList.remove("hidden"));
          toastTitle.textContent = data.title || "Aplicação Atualizada";
          toastBody.textContent = `Visualização pronta em: ${data.url}`;
          toastNotification.classList.remove("hidden");

          // Esconde automaticamente após 6 segundos
          setTimeout(() => {
            toastNotification.classList.add("hidden");
          }, 6000);
        }
      }
    } catch {}
  };

  eventsWs.onclose = () => {
    connStatusDot.className = "status-indicator offline";
    setTimeout(connectEventsWs, 3000);
  };
}

// --- Status, Túnel & IP Whitelist ---
async function loadTunnelInfo() {
  try {
    const res = await fetch("/api/apps");
    const data = await res.json();
    if (data.tunnel_url) {
      statusTunnelUrl.textContent = data.tunnel_url;
      btnCopyTunnel.onclick = () => {
        navigator.clipboard.writeText(data.tunnel_url);
        btnCopyTunnel.textContent = "Copiado!";
        setTimeout(() => btnCopyTunnel.textContent = "Copiar", 2000);
      };
    } else {
      statusTunnelUrl.textContent = "http://127.0.0.1:8765 (Local)";
    }
  } catch {}
}

async function loadIpStatus() {
  try {
    const res = await fetch("/api/ip/status");
    const data = await res.json();

    currentClientIp = data.client_ip;
    currentClientIpEl.textContent = data.client_ip;
    whitelistToggle.checked = Boolean(data.ip_whitelist_enabled);

    renderWhitelist(data.allowed_ips || []);
  } catch {}
}

function renderWhitelist(ips) {
  whitelistItems.innerHTML = "";
  if (!ips || ips.length === 0) {
    whitelistItems.innerHTML = '<li class="empty-state text-muted text-xs">Nenhum IP restrito. Qualquer IP com senha pode conectar.</li>';
    return;
  }

  ips.forEach(ip => {
    const li = document.createElement("li");
    li.className = "whitelist-item";
    li.innerHTML = `
      <span>${ip}</span>
      <button class="btn-xs btn-remove-ip" data-ip="${ip}">Remover</button>
    `;
    whitelistItems.appendChild(li);
  });

  document.querySelectorAll(".btn-remove-ip").forEach(btn => {
    btn.addEventListener("click", async () => {
      const ip = btn.getAttribute("data-ip");
      await updateWhitelist({ remove_ip: ip });
    });
  });
}

async function updateWhitelist(payload) {
  try {
    const res = await fetch("/api/ip/whitelist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      whitelistToggle.checked = Boolean(data.ip_whitelist_enabled);
      renderWhitelist(data.ip_whitelist);
    }
  } catch {}
}

function setupWhitelistControls() {
  whitelistToggle.addEventListener("change", async () => {
    await updateWhitelist({ enabled: whitelistToggle.checked });
  });

  btnWhitelistCurrentIp.addEventListener("click", async () => {
    if (currentClientIp) {
      await updateWhitelist({ ip: currentClientIp, enabled: true });
      btnWhitelistCurrentIp.textContent = "✅ IP Autorizado com Sucesso!";
      setTimeout(() => {
        btnWhitelistCurrentIp.textContent = "✅ Autorizar meu IP Atual na Whitelist";
      }, 3000);
    }
  });

  btnAddManualIp.addEventListener("click", async () => {
    const val = manualIpInput.value.trim();
    if (val) {
      await updateWhitelist({ ip: val });
      manualIpInput.value = "";
    }
  });

  btnRefreshVram.addEventListener("click", loadVramTelemetry);
}

async function loadVramTelemetry() {
  try {
    const res = await fetch("/api/vram");
    const data = await res.json();
    if (data.available) {
      vramText.textContent = `GPU: ${data.percent}% (${data.used_gb}/${data.total_gb} GB)`;
      metricVramUsage.textContent = `${data.used_gb} / ${data.total_gb} GB (${data.percent}%)`;
      metricVramBar.style.width = `${data.percent}%`;
      metricGpuTemp.textContent = `${data.temp_c} °C`;
      metricGpuUtil.textContent = `${data.gpu_util_pct} %`;
    } else {
      vramText.textContent = "GPU: N/A";
      metricVramUsage.textContent = "Indisponível";
      metricVramBar.style.width = "0%";
    }
  } catch {}
}

// --- Chat IA Opcional ---
function connectChatWs() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  chatWs = new WebSocket(`${protocol}//${window.location.host}/ws/chat`);

  let currentMsgEl = null;

  chatWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "start") {
      currentMsgEl = appendChatMessage("assistant", "");
    } else if (data.type === "chunk") {
      if (currentMsgEl) {
        currentMsgEl.textContent += data.content;
        chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
      }
    } else if (data.type === "done") {
      currentMsgEl = null;
    } else if (data.type === "error") {
      appendChatMessage("system-msg", `❌ ${data.content}`);
      currentMsgEl = null;
    }
  };

  chatWs.onclose = () => {
    setTimeout(connectChatWs, 3000);
  };
}

function sendWebChat() {
  const text = webChatInput.value.trim();
  if (!text || !chatWs || chatWs.readyState !== WebSocket.OPEN) return;

  appendChatMessage("user", text);
  webChatInput.value = "";
  chatWs.send(JSON.stringify({ message: text }));
}

function appendChatMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = content;
  chatMessagesContainer.appendChild(div);
  chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
  return div;
}

function setupChatControls() {
  btnSendWebChat.addEventListener("click", sendWebChat);
  webChatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendWebChat();
    }
  });

  btnClearChat.addEventListener("click", () => {
    chatMessagesContainer.innerHTML = `
      <div class="message system-msg">
        👋 Conversa limpa. Use a aba <strong>Terminal</strong> para interagir com o agy e claude no PC.
      </div>
    `;
  });
}
