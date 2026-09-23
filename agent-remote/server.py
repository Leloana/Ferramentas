import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx

from config import load_config, save_config, CONFIG_DIR
from auth import (
    COOKIE_NAME,
    verify_password,
    create_session_token,
    verify_session_token,
    is_authenticated,
    verify_ws_auth,
    get_client_ip,
    is_ip_allowed,
    check_ip_whitelist,
    require_auth
)
from llm import stream_chat_response
from terminal import execute_whitelisted_command, validate_command
from pty_manager import pty_manager
import mcp_server

app = FastAPI(title="Agent-Remote", version="1.0.0")

STATIC_DIR = CONFIG_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Armazenamento de sessões SSE do MCP e clientes WebSocket para broadcast de eventos
_MCP_SESSIONS: Dict[str, asyncio.Queue] = {}
_EVENT_CLIENTS: Set[WebSocket] = set()


async def broadcast_event(event_dict: Dict[str, Any]) -> None:
    """Envia evento em broadcast para todos os navegadores/celulares conectados."""
    for ws in list(_EVENT_CLIENTS):
        try:
            await ws.send_json(event_dict)
        except Exception:
            _EVENT_CLIENTS.discard(ws)


# --- Middleware de IP Whitelist ---
@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next):
    """Bloqueia requisições de IPs não autorizados quando a whitelist estiver ativada."""
    path = request.url.path
    if not path.startswith("/static"):
        client_ip = get_client_ip(request)
        if not is_ip_allowed(client_ip):
            if "text/html" in request.headers.get("accept", ""):
                html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>403 - Acesso Negado</title>
<style>
body{{font-family:sans-serif;background:#090d16;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}
.card{{background:#111827;border:1px solid #243048;border-radius:12px;padding:2rem;max-width:480px;text-align:center;box-shadow:0 10px 30px rgba(0,0,0,0.5);}}
h1{{color:#ef4444;font-size:1.5rem;margin-bottom:1rem;}}
code{{background:#1e293b;padding:0.25rem 0.6rem;border-radius:6px;color:#38bdf8;font-size:1.05rem;font-weight:bold;}}
p{{color:#94a3b8;line-height:1.6;margin:0.8rem 0;}}
</style>
</head>
<body>
<div class="card">
  <h1>🛑 Acesso Bloqueado por IP</h1>
  <p>A proteção por IP Whitelist está <strong>ativada</strong> no servidor.</p>
  <p>Seu endereço IP detectado é: <br><br><code>{client_ip}</code></p>
  <p>Para autorizar o acesso do seu celular, adicione este IP à lista <code>server.ip_whitelist</code> no arquivo <code>config.json</code>.</p>
</div>
</body>
</html>"""
                return HTMLResponse(content=html, status_code=403)
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": f"Acesso bloqueado: seu IP ({client_ip}) não está na whitelist."}
            )
    return await call_next(request)


# --- Middleware simples para autenticação na raiz ---
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Serve a página principal se autenticado, ou a tela de login."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Agent-Remote: static/index.html não encontrado</h1>", status_code=500)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# --- Autenticação HTTP ---
@app.post("/api/auth/login")
async def api_login(request: Request, response: Response):
    data = await request.json()
    pwd = data.get("password", "")
    if verify_password(pwd):
        token = create_session_token()
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=7 * 24 * 3600,
            samesite="lax",
            secure=False  # Funciona tanto em localhost quanto em Cloudflare HTTPS
        )
        return {"ok": True, "token": token}
    return JSONResponse(status_code=401, content={"ok": False, "error": "Senha incorreta"})


@app.post("/api/auth/logout")
async def api_logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/status")
async def api_auth_status(request: Request):
    auth = is_authenticated(request)
    return {"authenticated": auth}


# --- Gerenciamento de Aplicações ---
@app.get("/api/apps")
async def api_get_apps(request: Request):
    cfg = load_config()
    return {
        "apps": cfg.get("apps", []),
        "active_app": mcp_server.get_active_app(),
        "tunnel_url": mcp_server.get_tunnel_url(),
        "quick_actions": cfg.get("terminal", {}).get("quick_actions", [])
    }


@app.post("/api/apps/active")
async def api_set_active_app(request: Request):
    data = await request.json()
    app_id = data.get("app_id")
    if not app_id:
        raise HTTPException(status_code=400, detail="app_id é obrigatório")
    mcp_server.set_active_app(app_id)
    return {"ok": True, "active_app": app_id}


@app.post("/api/apps")
async def api_add_app(request: Request):
    data = await request.json()
    app_id = data.get("id") or str(uuid.uuid4())[:8]
    name = data.get("name", "Nova Aplicação")
    url = data.get("url", "http://127.0.0.1:8000")
    port = data.get("port", 8000)
    desc = data.get("desc", "")

    cfg = load_config()
    apps = cfg.get("apps", [])
    # Atualiza se existir, senão adiciona
    existing = next((a for a in apps if a["id"] == app_id), None)
    if existing:
        existing.update({"name": name, "url": url, "port": port, "desc": desc})
    else:
        apps.append({"id": app_id, "name": name, "url": url, "port": port, "desc": desc})

    cfg["apps"] = apps
    save_config(cfg)
# --- Gerenciamento de IP Whitelist ---
@app.get("/api/ip/status")
async def api_ip_status(request: Request):
    """Retorna o IP detectado do cliente e a lista de IPs autorizados."""
    client_ip = get_client_ip(request)
    cfg = load_config()
    server_cfg = cfg.get("server", {})
    return {
        "client_ip": client_ip,
        "is_allowed": is_ip_allowed(client_ip),
        "ip_whitelist_enabled": server_cfg.get("ip_whitelist_enabled", False),
        "allowed_ips": server_cfg.get("ip_whitelist", [])
    }


@app.post("/api/ip/whitelist")
async def api_update_ip_whitelist(request: Request):
    """Adiciona ou remove um IP da whitelist e permite ligar/desligar."""
    require_auth(request)
    data = await request.json()
    new_ip = data.get("ip", "").strip()
    enable = data.get("enabled")
    remove_ip = data.get("remove_ip", "").strip()

    cfg = load_config()
    server_cfg = cfg.setdefault("server", {})
    whitelist = server_cfg.setdefault("ip_whitelist", [])

    if new_ip and new_ip not in whitelist:
        whitelist.append(new_ip)

    if remove_ip and remove_ip in whitelist:
        whitelist.remove(remove_ip)

    if enable is not None:
        server_cfg["ip_whitelist_enabled"] = bool(enable)

    save_config(cfg)
    return {
        "ok": True,
        "ip_whitelist_enabled": server_cfg.get("ip_whitelist_enabled"),
        "ip_whitelist": whitelist
    }


# --- Endpoints da Aba MCP ---
@app.get("/api/mcp/tools")
async def api_get_mcp_tools():
    """Retorna o catálogo de ferramentas MCP disponíveis."""
    return {"tools": mcp_server.MCP_TOOLS}


@app.post("/api/mcp/call")
async def api_call_mcp_tool(request: Request):
    """Executa uma ferramenta MCP a partir da interface web."""
    data = await request.json()
    name = data.get("name", "")
    args = data.get("arguments", {})
    result = await mcp_server.handle_tool_call(name, args)
    return {
        "ok": True,
        "name": name,
        "result": result,
        "history": mcp_server.get_tool_call_history()
    }


@app.get("/api/mcp/history")
async def api_get_mcp_history():
    """Retorna o histórico de chamadas de ferramentas MCP."""
    return {
        "history": mcp_server.get_tool_call_history(),
        "notifications": mcp_server.get_chat_notifications()
    }


# --- Telemetria e Hardware (VRAM) ---
@app.get("/api/vram")
async def api_get_vram():
    """Lê telemetria da GPU via nvidia-smi de forma assíncrona."""
    output = []
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi", "--query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            parts = stdout.decode().strip().split(",")
            if len(parts) >= 4:
                used = float(parts[0].strip())
                total = float(parts[1].strip())
                temp = parts[2].strip()
                util = parts[3].strip()
                return {
                    "available": True,
                    "used_mb": used,
                    "total_mb": total,
                    "used_gb": round(used / 1024, 1),
                    "total_gb": round(total / 1024, 1),
                    "percent": round((used / total) * 100, 1),
                    "temp_c": temp,
                    "gpu_util_pct": util
                }
    except Exception:
        pass
    return {"available": False, "msg": "GPU não detectada ou nvidia-smi indisponível"}


# --- Modelos & Configuração LLM ---
@app.get("/api/models")
async def api_get_models():
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    return {
        "current": llm_cfg,
        "providers": [
            {"id": "ollama", "name": "Ollama Local (qwen3.5, etc.)"},
            {"id": "gemini", "name": "Google Gemini (gemini-2.5, etc.)"},
            {"id": "openai", "name": "OpenAI (gpt-4o, etc.)"},
            {"id": "anthropic", "name": "Anthropic Claude (claude-3-7-sonnet)"},
            {"id": "groq", "name": "Groq (ultra fast)"},
            {"id": "openrouter", "name": "OpenRouter (multi-provider)"},
            {"id": "custom", "name": "Custom OpenAI-Compatible"}
        ]
    }


@app.post("/api/models")
async def api_save_model(request: Request):
    data = await request.json()
    cfg = load_config()
    cfg["llm"].update(data)
    save_config(cfg)
    return {"ok": True, "llm": cfg["llm"]}


# --- Proxy Reverso Dinâmico para Qualquer Porta Local ---
@app.api_route("/proxy/port/{port}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.api_route("/proxy/port/{port}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def dynamic_port_proxy(port: int, request: Request, path: str = ""):
    """
    Proxy reverso universal para qualquer porta local (ex: 3000, 5173, 8080).
    Permite testar qualquer site gerado pelo agente através do Cloudflare Tunnel sem Mixed Content.
    """
    target_url = f"http://127.0.0.1:{port}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}

    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=True
            )

            excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
            resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}

            content = resp.content
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                base_tag = f'<base href="/proxy/port/{port}/">'.encode("utf-8")
                if b"<head>" in content:
                    content = content.replace(b"<head>", b"<head>" + base_tag, 1)
                elif b"<HEAD>" in content:
                    content = content.replace(b"<HEAD>", b"<HEAD>" + base_tag, 1)

            return Response(content=content, status_code=resp.status_code, headers=resp_headers)
    except httpx.ConnectError:
        return HTMLResponse(
            f"<div style='font-family:sans-serif;padding:2rem;color:#f87171;background:#0f172a;height:100vh;box-sizing:border-box;'>"
            f"<h3>⚠️ Nenhuma aplicação respondendo na porta {port}</h3>"
            f"<p style='color:#94a3b8;'>Inicie o servidor no terminal (ex: <code>npm run dev</code>, <code>python app.py</code>) e recarregue a aba.</p>"
            f"</div>",
            status_code=502
        )
    except Exception as e:
        return HTMLResponse(f"Erro no proxy: {str(e)}", status_code=500)


# --- Proxy Reverso para Aplicações Pré-registradas no config.json ---
@app.api_route("/proxy/{app_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def app_reverse_proxy(app_id: str, path: str, request: Request):
    """
    Encaminha requisições da web HTTPS para o serviço HTTP local correspondente.
    """
    cfg = load_config()
    app_info = next((a for a in cfg.get("apps", []) if a["id"] == app_id), None)
    if not app_info:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada no proxy")

    target_base = app_info["url"].rstrip("/")
    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}

    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=True
            )
            excluded_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
            resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}

            return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
    except httpx.ConnectError:
        return HTMLResponse(
            f"<div style='font-family:sans-serif;padding:2rem;color:#ff5555;'>"
            f"<h3>⚠️ Aplicação '{app_info['name']}' não está em execução</h3>"
            f"<p>Certifique-se de iniciar o servidor local na porta {app_info.get('port', 8000)}.</p>"
            f"</div>",
            status_code=502
        )
    except Exception as e:
        return HTMLResponse(f"Erro no proxy: {str(e)}", status_code=500)


# --- Endpoints de Preview (Sincronização MCP & Web UI) ---
@app.get("/api/preview")
async def api_get_preview():
    """Retorna a URL e metadados da aplicação ativa exibida no preview."""
    return mcp_server.get_preview_state()


@app.post("/api/preview")
async def api_set_preview(request: Request):
    """Permite alterar a aplicação ativa diretamente pela interface web."""
    require_auth(request)
    data = await request.json()
    raw_url = str(data.get("url", "")).strip()
    title = data.get("title", "").strip() or "Aplicação Remota"

    if raw_url.isdigit():
        norm_url = f"http://localhost:{raw_url}"
    elif raw_url.startswith("localhost:") or raw_url.startswith("127.0.0.1:"):
        norm_url = f"http://{raw_url}"
    elif not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        norm_url = f"http://{raw_url}"
    else:
        norm_url = raw_url

    state = {
        "url": norm_url,
        "title": title,
        "app_id": data.get("app_id", "custom"),
        "updated_at": time.strftime("%H:%M:%S")
    }
    mcp_server.save_preview_state(state)
    await broadcast_event({
        "type": "preview_updated",
        "url": norm_url,
        "title": title,
        "app_id": state["app_id"]
    })
    return {"ok": True, "preview": state}


@app.post("/api/internal/preview-update")
async def api_internal_preview_update(request: Request):
    """Recebe eventos internos disparados por chamadas MCP em outro processo."""
    data = await request.json()
    url = data.get("url", "")
    title = data.get("title", "")
    app_id = data.get("app_id", "custom")
    await broadcast_event({
        "type": "preview_updated",
        "url": url,
        "title": title,
        "app_id": app_id
    })
    return {"ok": True}


# --- WebSockets: Chat com IA ---
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    if not await verify_ws_auth(websocket):
        await websocket.send_json({"type": "error", "content": "Não autenticado"})
        await websocket.close(code=1008)
        return

    history: List[Dict[str, str]] = []

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            user_msg = data.get("message", "").strip()
            if not user_msg:
                continue

            history.append({"role": "user", "content": user_msg})

            provider = data.get("provider")
            model = data.get("model")
            api_key = data.get("api_key")
            base_url = data.get("base_url")

            # Avisa início da resposta
            await websocket.send_json({"type": "start"})

            full_reply = ""
            async for token in stream_chat_response(
                messages=history,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url
            ):
                full_reply += token
                await websocket.send_json({"type": "chunk", "content": token})

            history.append({"role": "assistant", "content": full_reply})
            await websocket.send_json({"type": "done", "full_content": full_reply})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


# --- WebSockets: Terminal Seguro (Whitelist) ---
@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    await websocket.accept()
    if not await verify_ws_auth(websocket):
        await websocket.send_json({"type": "output", "text": "[ERRO] Acesso negado: faça login primeiro.\n"})
        await websocket.close(code=1008)
        return

    await websocket.send_json({
        "type": "output",
        "text": "🟢 Terminal Remoto Seguro Ativo (Whitelist habilitada).\nDigite comandos como 'git status', 'nvidia-smi' ou use os botões rápidos.\n\n"
    })

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            cmd = data.get("command", "").strip()
            if not cmd:
                continue

            await websocket.send_json({"type": "start"})
            async for output_line in execute_whitelisted_command(cmd):
                await websocket.send_json({"type": "output", "text": output_line})
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "output", "text": f"\n[ERRO WS] {str(e)}\n"})
        except Exception:
            pass


# --- WebSockets: Terminal PTY Interativo (xterm.js para agy, claude e bash) ---
@app.websocket("/ws/pty")
async def websocket_pty(websocket: WebSocket, session_id: str = "default"):
    await websocket.accept()
    if not await verify_ws_auth(websocket):
        await websocket.send_text("[ERRO] Acesso negado: faça login primeiro.\r\n")
        await websocket.close(code=1008)
        return

    loop = asyncio.get_running_loop()
    session = pty_manager.get_or_create(session_id=session_id, cols=80, rows=24, loop=loop)

    output_queue: asyncio.Queue = asyncio.Queue()
    session.subscribe(output_queue)

    async def pty_reader():
        try:
            while True:
                chunk = await output_queue.get()
                await websocket.send_text(chunk.decode("utf-8", errors="replace"))
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
        except Exception:
            pass

    reader_task = asyncio.create_task(pty_reader())

    try:
        while True:
            msg = await websocket.receive_text()
            if msg.startswith("{") and "type" in msg:
                try:
                    payload = json.loads(msg)
                    msg_type = payload.get("type")
                    if msg_type == "resize":
                        cols = int(payload.get("cols", 80))
                        rows = int(payload.get("rows", 24))
                        session.resize(cols, rows)
                        continue
                    elif msg_type == "input":
                        data_str = payload.get("data", "")
                        session.write(data_str.encode("utf-8"))
                        continue
                except json.JSONDecodeError:
                    pass

            session.write(msg.encode("utf-8"))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        session.unsubscribe(output_queue)
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass


# --- WebSockets: Canal de Eventos e Telemetria em Tempo Real ---
@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    if not await verify_ws_auth(websocket):
        await websocket.close(code=1008)
        return

    _EVENT_CLIENTS.add(websocket)
    try:
        # Envia estado inicial do preview
        state = mcp_server.get_preview_state()
        await websocket.send_json({
            "type": "preview_updated",
            "url": state.get("url", ""),
            "title": state.get("title", ""),
            "app_id": state.get("app_id", "")
        })

        while True:
            raw = await websocket.receive_text()
            if raw == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _EVENT_CLIENTS.discard(websocket)


# --- MCP Server (Server-Sent Events) ---
@app.get("/mcp/sse")
async def mcp_sse_endpoint():
    """Endpoint SSE para inicialização do transporte MCP."""
    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    _MCP_SESSIONS[session_id] = queue

    async def event_generator():
        # Envia o endpoint de mensagens para o cliente MCP
        yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
        while True:
            msg = await queue.get()
            yield f"event: message\ndata: {json.dumps(msg)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/mcp/messages")
async def mcp_message_handler(request: Request, session_id: Optional[str] = None):
    """Trata requisições JSON-RPC 2.0 vindas de clientes MCP."""
    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")

    response_data = None

    if method == "initialize":
        response_data = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "agent-remote-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {}}
            }
        }
    elif method == "tools/list":
        response_data = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": mcp_server.MCP_TOOLS}
        }
    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {})
        result_text = await mcp_server.handle_tool_call(name, args)
        response_data = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": result_text}]}
        }
    else:
        response_data = {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    # Se houver sessão SSE ativa, despacha por ela; senão responde HTTP direto
    if session_id and session_id in _MCP_SESSIONS:
        await _MCP_SESSIONS[session_id].put(response_data)
        return {"status": "dispatched"}

    return response_data


# Monta a pasta estática por último
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
