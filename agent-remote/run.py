#!/usr/bin/env python3
import asyncio
import io
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from config import load_config
import mcp_server

cloudflared_proc = None


def print_banner(local_url: str, public_url: str = None):
    print("\n" + "=" * 65)
    print(" 🌐  AGENT-REMOTE — CONTROLE WEB & CENTRAL DE APLICAÇÕES")
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
        print(" ℹ️  Túnel Cloudflare não iniciado (cloudflared não encontrado).")
        print("    Para acessar pelo celular fora de casa, instale o cloudflared:")
        print("    - Windows: winget install --id Cloudflare.cloudflared")
        print("    - Linux:   sudo apt install cloudflared")
    print("=" * 65)
    print(" Pressione Ctrl+C para encerrar o servidor e o túnel.")
    print("=" * 65 + "\n")


def start_cloudflare_tunnel(local_port: int):
    global cloudflared_proc

    if not shutil.which("cloudflared"):
        return None

    cmd = ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{local_port}"]
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
    while time.time() - start_time < 15:
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
            cloudflared_proc.terminate()
            cloudflared_proc.wait(timeout=3)
        except Exception:
            cloudflared_proc.kill()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

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
