#!/usr/bin/env python3
import asyncio
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from config import load_config
import mcp_server

cloudflared_proc = None
IS_WINDOWS = sys.platform == "win32"
BASE_DIR = Path(__file__).resolve().parent


def sync_mcp_config() -> None:
    """Garante que .mcp.json use o interpretador Python e caminhos nativos do SO atual."""
    mcp_script = BASE_DIR / "mcp_server.py"

    if IS_WINDOWS:
        venv_python = BASE_DIR / "venv" / "Scripts" / "python.exe"
    else:
        venv_python = BASE_DIR / "venv" / "bin" / "python"

    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    mcp_config = {
        "mcpServers": {
            "agent-remote": {
                "command": python_bin,
                "args": [str(mcp_script)]
            }
        }
    }

    # Atualiza tanto na pasta do agent-remote quanto no repo pai
    for target in [BASE_DIR / ".mcp.json", BASE_DIR.parent / ".mcp.json"]:
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(mcp_config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


def find_or_install_cloudflared() -> str | None:
    """Localiza o executável do Cloudflare Tunnel ou faz download automático no Windows."""
    # 1. Procura no PATH
    for name in ["cloudflared", "cloudflared.exe"]:
        found = shutil.which(name)
        if found:
            return found

    # 2. Procura no diretório local do agent-remote
    local_bin = BASE_DIR / ("cloudflared.exe" if IS_WINDOWS else "cloudflared")
    if local_bin.exists():
        return str(local_bin)

    # 3. Locais comuns no Windows
    if IS_WINDOWS:
        common_paths = [
            r"C:\Program Files\cloudflared\cloudflared.exe",
            r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            str(Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe")
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p

        # 4. Download automático no Windows (Zero-Configuração)
        print("[agent-remote] cloudflared.exe não encontrado. Baixando versão oficial para Windows...")
        download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        try:
            import urllib.request
            urllib.request.urlretrieve(download_url, str(local_bin))
            print(f"[agent-remote] cloudflared.exe salvo em: {local_bin}")
            return str(local_bin)
        except Exception as e:
            print(f"[agent-remote] Falha no download automático do cloudflared: {e}")
            print("  Instale manualmente no Windows executando no PowerShell: winget install --id Cloudflare.cloudflared")
            return None

    return None


def print_banner(local_url: str, public_url: str = None):
    os_name = "Windows Nativo" if IS_WINDOWS else "Linux"
    print("\n" + "=" * 65)
    print(f" 🌐  AGENT-REMOTE — CONTROLE WEB [{os_name.upper()}]")
    print("=" * 65)
    print(f" 🏠 Acesso Local:     {local_url}")
    if public_url:
        print(f" ☁️  Acesso Remoto:    {public_url}")
        print(" 🔒  Túnel Ativo:     Cloudflare Quick Tunnel (HTTPS Seguro)")
        print("-" * 65)
        print(" 📱 Escaneie o QR Code abaixo com a câmera do seu celular:")
        try:
            import qrcode
            qr = qrcode.QRCode()
            qr.add_data(public_url)
            f = io.StringIO()
            qr.print_ascii(out=f, invert=True)
            f.seek(0)
            print(f.read())
        except Exception:
            pass
    else:
        print(" ℹ️  Túnel Cloudflare não iniciado.")
        if IS_WINDOWS:
            print("    Para acessar pelo celular fora de casa, execute no PowerShell:")
            print("    winget install --id Cloudflare.cloudflared")
        else:
            print("    Para instalar o cloudflared no Linux: sudo apt install cloudflared")
    print("=" * 65)
    print(" Pressione Ctrl+C para encerrar o servidor e o túnel.")
    print("=" * 65 + "\n")


def start_cloudflare_tunnel(local_port: int) -> str | None:
    global cloudflared_proc

    bin_path = find_or_install_cloudflared()
    if not bin_path:
        return None

    cmd = [bin_path, "tunnel", "--url", f"http://127.0.0.1:{local_port}"]
    cloudflared_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    tunnel_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    # Aguarda a URL nos primeiros segundos de log
    start_time = time.time()
    while time.time() - start_time < 20:
        line = cloudflared_proc.stdout.readline()
        if not line:
            break
        match = url_pattern.search(line)
        if match:
            tunnel_url = match.group(0)
            break

    if tunnel_url:
        mcp_server.set_tunnel_url(tunnel_url)
        return tunnel_url

    return None


def cleanup(sig=None, frame=None):
    global cloudflared_proc
    if cloudflared_proc:
        print("\n[agent-remote] Encerrando túnel Cloudflare...")
        try:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(cloudflared_proc.pid)], capture_output=True)
            else:
                cloudflared_proc.terminate()
                cloudflared_proc.wait(timeout=3)
        except Exception:
            try:
                cloudflared_proc.kill()
            except Exception:
                pass
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, cleanup)
    try:
        signal.signal(signal.SIGTERM, cleanup)
    except Exception:
        pass

    # Sincroniza caminhos do MCP para o SO atual
    sync_mcp_config()

    cfg = load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = server_cfg.get("port", 8765)

    cf_enabled = cfg.get("cloudflare", {}).get("enabled", True)
    public_url = None

    if cf_enabled:
        print("[agent-remote] Verificando e iniciando Cloudflare Tunnel...")
        public_url = start_cloudflare_tunnel(port)

    local_url = f"http://{host}:{port}"
    print_banner(local_url, public_url)

    import uvicorn
    uvicorn.run("server:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
