#!/usr/bin/env python3
"""
receiver.py  --  Abre no navegador padrao do PC uma URL recebida do celular.

Cross-platform: funciona em Windows, Linux e macOS.

Uso principal (modo --once, disparado por SSH a partir do Termux):
    echo "https://exemplo.com" | python receiver.py --once
    # ou passando como argumento:
    python receiver.py --once "https://exemplo.com"

Modo daemon (opcional, mantem um listener TCP local vivo):
    python receiver.py --daemon          # escuta em 127.0.0.1:8765
Cada conexao envia uma URL (uma linha) e o daemon a abre. Util se voce
preferir um processo persistente em vez de spawnar Python a cada SSH.

Log: <home>/.handoff/daemon.log
"""
import sys
import os
import socket
import logging
import webbrowser
from pathlib import Path

HANDOFF_DIR = Path.home() / ".handoff"
LOG_FILE = HANDOFF_DIR / "daemon.log"
DAEMON_HOST = os.environ.get("HANDOFF_HOST", "127.0.0.1")
DAEMON_PORT = int(os.environ.get("HANDOFF_PORT", "8765"))


def setup_logging():
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def open_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    # Aceita apenas esquemas seguros para evitar abrir caminhos/arbitrario.
    if not (url.startswith("http://") or url.startswith("https://")):
        logging.warning(f"IGNORADO (esquema nao permitido): {url!r}")
        return False
    try:
        # webbrowser usa o navegador padrao em qualquer SO.
        opened = webbrowser.open(url)
        if not opened and os.name == "nt":
            # Fallback Windows: associacao do shell.
            os.startfile(url)  # type: ignore[attr-defined]
        logging.info(f"OK: {url}")
        return True
    except Exception as e:
        logging.error(f"FAIL: {url} -> {e}")
        return False


def collect_urls():
    """Junta URLs de argumentos posicionais e do stdin (se encanado)."""
    urls = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not sys.stdin.isatty():
        urls += [ln.strip() for ln in sys.stdin if ln.strip()]
    return [u for u in urls if u]


def handle_stdin_and_args():
    """Modo --once: abre a URL DIRETAMENTE neste processo.

    Atencao: se chamado a partir de uma sessao SSH (servico sshd, sessao 0),
    o navegador abre numa area de trabalho NAO visivel. Para o handoff real,
    use --send (envia ao daemon que roda na sessao interativa do usuario).
    """
    any_opened = any(open_url(u) for u in collect_urls())
    return 0 if any_opened else 1


def send_mode():
    """Modo --send: encaminha as URLs ao daemon local (sessao interativa).

    Assim o navegador abre na area de trabalho visivel do usuario, mesmo
    quando o disparo vem de uma sessao SSH.
    """
    urls = collect_urls()
    if not urls:
        return 1
    try:
        sock = socket.create_connection((DAEMON_HOST, DAEMON_PORT), timeout=3)
    except OSError as e:
        msg = (f"Daemon nao esta rodando em {DAEMON_HOST}:{DAEMON_PORT} ({e}). "
               f"Inicie-o com: pythonw receiver.py --daemon")
        logging.error(msg)
        print(msg, file=sys.stderr)
        return 1
    with sock:
        sock.sendall(("\n".join(urls) + "\n").encode("utf-8"))
    logging.info(f"SEND -> daemon: {urls}")
    return 0


def daemon_loop():
    """Escuta TCP local e abre cada URL recebida (uma por conexao/linha)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind((DAEMON_HOST, DAEMON_PORT))
    except OSError as e:
        # Porta ocupada => provavelmente o daemon ja esta rodando. Sai limpo.
        logging.info(f"Bind falhou ({e}); daemon provavelmente ja ativo. Saindo.")
        print(f"Daemon ja parece estar rodando em {DAEMON_HOST}:{DAEMON_PORT}.")
        return
    srv.listen(5)
    logging.info(f"Daemon ouvindo em {DAEMON_HOST}:{DAEMON_PORT}")
    print(f"Handoff daemon ouvindo em {DAEMON_HOST}:{DAEMON_PORT}", flush=True)
    while True:
        try:
            conn, _ = srv.accept()
            with conn:
                data = conn.recv(8192).decode("utf-8", "replace")
                for line in data.splitlines():
                    open_url(line)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Erro no daemon: {e}")
    srv.close()


def main():
    setup_logging()
    if "--daemon" in sys.argv:
        logging.info("Daemon iniciado")
        daemon_loop()
        return 0
    if "--send" in sys.argv:
        return send_mode()
    # padrao = modo --once (abre direto; ver aviso na funcao)
    return handle_stdin_and_args()


if __name__ == "__main__":
    sys.exit(main())
