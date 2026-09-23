import asyncio
import json
import os
import sys
from typing import Any, Dict, List
from config import load_config, save_config
from terminal import execute_whitelisted_command

# Armazena estado compartilhado em memória
_ACTIVE_APP = "tts_platform_pt"
_TUNNEL_URL = ""
_CHAT_NOTIFICATIONS: List[str] = []


def get_active_app() -> str:
    global _ACTIVE_APP
    return _ACTIVE_APP


def set_active_app(app_id: str) -> None:
    global _ACTIVE_APP
    _ACTIVE_APP = app_id


def get_tunnel_url() -> str:
    global _TUNNEL_URL
    return _TUNNEL_URL


def set_tunnel_url(url: str) -> None:
    global _TUNNEL_URL
    _TUNNEL_URL = url


def add_chat_notification(msg: str) -> None:
    global _CHAT_NOTIFICATIONS
    _CHAT_NOTIFICATIONS.append(msg)
    if len(_CHAT_NOTIFICATIONS) > 100:
        _CHAT_NOTIFICATIONS.pop(0)


def get_chat_notifications() -> List[str]:
    global _CHAT_NOTIFICATIONS
    return list(_CHAT_NOTIFICATIONS)


_TOOL_CALL_HISTORY: List[Dict[str, Any]] = []


def get_tool_call_history() -> List[Dict[str, Any]]:
    global _TOOL_CALL_HISTORY
    return list(_TOOL_CALL_HISTORY)


def record_tool_call(name: str, arguments: Dict[str, Any], result: str) -> None:
    global _TOOL_CALL_HISTORY
    import time
    _TOOL_CALL_HISTORY.append({
        "timestamp": time.strftime("%H:%M:%S"),
        "name": name,
        "arguments": arguments,
        "result": result
    })
    if len(_TOOL_CALL_HISTORY) > 50:
        _TOOL_CALL_HISTORY.pop(0)


MCP_TOOLS = [
    {
        "name": "list_applications",
        "description": "Lista todas as ferramentas e aplicações web registradas no Agent-Remote com suas portas e status.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "set_active_application",
        "description": "Altera qual aplicação web é exibida na aba de Live Preview do Agent-Remote (ex: 'tts_platform_pt', 'karaoke', 'comfyui').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "O ID da aplicação (ex: tts_platform_pt, karaoke, comfyui)"
                }
            },
            "required": ["app_id"]
        }
    },
    {
        "name": "get_system_status",
        "description": "Verifica o consumo de VRAM da GPU (nvidia-smi), uso de memória e status dos serviços.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "execute_whitelisted_command",
        "description": "Executa um comando seguro da whitelist no terminal do host (ex: git status, git pull, nvidia-smi, python scripts/executar_projeto.py ...).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "O comando a executar (deve respeitar a whitelist de segurança)"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "send_remote_chat",
        "description": "Envia uma mensagem ou notificação diretamente para a tela de chat do usuário no celular/navegador remoto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "O conteúdo da mensagem a ser exibida na interface remota"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "get_tunnel_url",
        "description": "Retorna a URL pública HTTPS do Cloudflare Tunnel ativa no momento.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


async def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Executa a ferramenta MCP solicitada e retorna texto."""
    cfg = load_config()
    result = ""

    if name == "list_applications":
        apps = cfg.get("apps", [])
        active = get_active_app()
        result = json.dumps({"active_app": active, "applications": apps}, indent=2, ensure_ascii=False)

    elif name == "set_active_application":
        app_id = arguments.get("app_id", "").strip()
        apps = [a["id"] for a in cfg.get("apps", [])]
        if app_id in apps:
            set_active_app(app_id)
            result = f"Aplicação ativa alterada com sucesso para '{app_id}'."
        else:
            result = f"Aplicação '{app_id}' não encontrada. Opções disponíveis: {', '.join(apps)}"

    elif name == "get_system_status":
        lines = []
        async for line in execute_whitelisted_command("nvidia-smi"):
            lines.append(line)
        result = "".join(lines)

    elif name == "execute_whitelisted_command":
        cmd = arguments.get("command", "").strip()
        lines = []
        async for line in execute_whitelisted_command(cmd):
            lines.append(line)
        result = "".join(lines)

    elif name == "send_remote_chat":
        msg = arguments.get("message", "").strip()
        add_chat_notification(msg)
        result = f"Mensagem enviada para a interface remota: '{msg}'"

    elif name == "get_tunnel_url":
        url = get_tunnel_url()
        if url:
            result = f"URL pública ativa: {url}"
        else:
            result = "Nenhum Cloudflare Tunnel público detectado no momento (rodando localmente em http://127.0.0.1:8765)."
    else:
        result = f"Ferramenta desconhecida: {name}"

    record_tool_call(name, arguments, result)
    return result


async def stdio_server_loop():
    """Servidor MCP sobre STDIO para ser conectado como MCP Server por qualquer agente (Cursor, Claude, Antigravity, etc.)."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            break
        line = line_bytes.decode("utf-8").strip()
        if not line:
            continue

        try:
            req = json.loads(line)
            method = req.get("method")
            msg_id = req.get("id")

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "agent-remote-mcp", "version": "1.0.0"},
                        "capabilities": {"tools": {}}
                    }
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                pass  # Apenas confirmação

            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"tools": MCP_TOOLS}
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name", "")
                args = params.get("arguments", {})
                result_text = await handle_tool_call(name, args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}]
                    }
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": req.get("id") if 'req' in locals() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(stdio_server_loop())
