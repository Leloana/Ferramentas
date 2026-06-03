#!/usr/bin/env python3
"""
agente.py  --  Agente Windows do Ecossistema Hibrido (Marco 1).

Evolui o antigo receiver.py: em vez de so abrir URLs, recebe o *descritor de
handoff* (independente de plataforma, ver PLANO.md secao 4) e resolve o
equivalente local pela Tabela de Apps-Equivalentes (secao 4) com fallback
automatico por esquema/MIME.

  Descritor (uma linha JSON por evento):
    {
      "tipo": "midia"|"url"|"arquivo"|"pasta"|"texto"|"mapa"|"contato",
      "app_origem": "com.google.android.youtube",
      "dados": { "url": "...", "pos_segundos": 412, "caminho": "/DCIM/..." },
      "timestamp": 1730000000
    }

LICAO DA SESSAO 0/1 (PLANO.md secao 3): quem abre UI/apps tem que rodar na
sessao INTERATIVA do usuario. Por isso o agente roda como daemon (via
start-agente.vbs na pasta Startup) e o disparo vindo do celular (SSH, que cai
na sessao 0 do servico) apenas ENTREGA o descritor ao daemon pelo modo --send.
O daemon -- na sessao do usuario -- e quem abre navegador/Explorer/apps.

Modos:
    python agente.py --daemon          # escuta em 127.0.0.1:8765 (sessao do usuario)
    python agente.py --send            # le 1 descritor (JSON) do stdin e envia ao daemon
    python agente.py --send '<json>'   # idem, descritor como argumento
    python agente.py --once '<json>'   # executa direto neste processo (debug; ver aviso)

Compatibilidade: se a linha recebida NAO for JSON, e tratada como URL pura
(comportamento antigo do receiver.py).

Config: <pasta-do-script>/config.json (ver config.example.json).
Log:    <home>/.handoff/agente.log
"""
import sys
import os
import json
import socket
import logging
import webbrowser
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

HANDOFF_DIR = Path.home() / ".handoff"
LOG_FILE = HANDOFF_DIR / "agente.log"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

DAEMON_HOST = os.environ.get("HANDOFF_HOST", "127.0.0.1")
DAEMON_PORT = int(os.environ.get("HANDOFF_PORT", "8765"))

IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- #
# Infra: logging, config, feedback                                            #
# --------------------------------------------------------------------------- #
def setup_logging():
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def load_config() -> dict:
    """Le config.json (path mapping, dispositivos confiaveis). Degrada p/ {}."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning(f"config.json invalido ({e}); usando padroes.")
        return {}


def notify(titulo: str, msg: str):
    """Feedback visual best-effort (toast Windows). Degrada para log/print."""
    logging.info(f"{titulo}: {msg}")
    print(f"[{titulo}] {msg}", flush=True)
    if not IS_WINDOWS:
        return
    # Toast nativo via PowerShell (sem dependencias externas). Best-effort.
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType=WindowsRuntime] | Out-Null;"
        "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$x=$t.GetElementsByTagName('text');"
        f"$x.Item(0).AppendChild($t.CreateTextNode('{_ps_escape(titulo)}')) | Out-Null;"
        f"$x.Item(1).AppendChild($t.CreateTextNode('{_ps_escape(msg)}')) | Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'Ecossistema Handoff').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($t));"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logging.debug(f"Toast falhou (ignorado): {e}")


def _ps_escape(s: str) -> str:
    """Escapa string para uso dentro de aspas simples do PowerShell."""
    return (s or "").replace("'", "''")


# --------------------------------------------------------------------------- #
# Acoes locais (lado Windows)                                                  #
# --------------------------------------------------------------------------- #
def open_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        logging.warning(f"IGNORADO (esquema nao permitido): {url!r}")
        return False
    try:
        opened = webbrowser.open(url)
        if not opened and IS_WINDOWS:
            os.startfile(url)  # type: ignore[attr-defined]
        logging.info(f"URL aberta: {url}")
        return True
    except Exception as e:
        logging.error(f"FAIL url {url} -> {e}")
        return False


def open_path(win_path: str) -> bool:
    """Abre arquivo ou pasta no app/Explorer padrao do Windows."""
    win_path = (win_path or "").strip()
    if not win_path:
        return False
    try:
        if IS_WINDOWS:
            p = Path(win_path)
            if p.is_dir():
                # explorer.exe sempre retorna codigo != 0; nao usar check.
                subprocess.Popen(["explorer.exe", str(p)])
            else:
                os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            # Fallback Linux/macOS (util para dev fora do PC de casa).
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, win_path])
        logging.info(f"Caminho aberto: {win_path}")
        return True
    except Exception as e:
        logging.error(f"FAIL caminho {win_path} -> {e}")
        return False


def set_clipboard(texto: str) -> bool:
    """Coloca texto no clipboard. Windows: clip.exe; Linux: xclip; macOS: pbcopy."""
    if texto is None:
        return False
    try:
        if IS_WINDOWS:
            cmd = ["clip"]
        elif sys.platform == "darwin":
            cmd = ["pbcopy"]
        else:
            cmd = ["xclip", "-selection", "clipboard"]
        proc = subprocess.run(cmd, input=texto.encode("utf-8"), check=False)
        ok = proc.returncode == 0
        logging.info(f"Clipboard {'OK' if ok else 'FAIL'} ({len(texto)} chars)")
        return ok
    except Exception as e:
        logging.error(f"FAIL clipboard -> {e}")
        return False


# --------------------------------------------------------------------------- #
# Mapeamento de caminhos Android <-> Windows                                   #
# --------------------------------------------------------------------------- #
def map_android_to_windows(android_path: str, config: dict) -> str:
    """Converte um caminho Android no caminho equivalente no Windows.

    Usa config["mapeamento_caminhos"] = [{"android": "...", "windows": "..."}],
    escolhendo o prefixo Android mais longo que casa. Sem regra casando, devolve
    o caminho original (degradacao graciosa).
    """
    android_path = (android_path or "").strip()
    if not android_path:
        return android_path
    regras = config.get("mapeamento_caminhos", []) or []
    # prefixo mais especifico primeiro
    regras = sorted(regras, key=lambda r: len(r.get("android", "")), reverse=True)
    for r in regras:
        a = r.get("android", "")
        w = r.get("windows", "")
        if a and android_path.startswith(a):
            resto = android_path[len(a):]
            win = (w.rstrip("\\/") + "\\" + resto.lstrip("/")) if resto else w
            return win.replace("/", "\\") if IS_WINDOWS else win
        if a and android_path == a.rstrip("/"):
            return w
    logging.info(f"Sem mapeamento p/ {android_path!r}; usando original.")
    return android_path


# --------------------------------------------------------------------------- #
# Tabela de Apps-Equivalentes                                                  #
# --------------------------------------------------------------------------- #
def youtube_id(url: str):
    """Extrai o id do video de uma URL do YouTube (varias formas)."""
    try:
        u = urlparse(url)
    except Exception:
        return None
    host = (u.netloc or "").lower()
    if "youtu.be" in host:
        vid = u.path.lstrip("/").split("/")[0]
        return vid or None
    if "youtube.com" in host:
        if u.path.startswith("/watch"):
            v = parse_qs(u.query).get("v", [None])[0]
            return v
        if u.path.startswith("/shorts/") or u.path.startswith("/embed/"):
            return u.path.split("/")[2] if len(u.path.split("/")) > 2 else None
    return None


def handle_midia(dados: dict, config: dict) -> bool:
    """midia: YouTube com timestamp, Spotify/outros como URL."""
    url = dados.get("url", "")
    pos = dados.get("pos_segundos")
    vid = youtube_id(url)
    if vid:
        alvo = f"https://youtu.be/{vid}"
        if isinstance(pos, (int, float)) and pos > 0:
            alvo += f"?t={int(pos)}"
        ok = open_url(alvo)
        notify("Handoff: video", f"Continuando no PC em t={int(pos or 0)}s")
        return ok
    # Fallback: trata como URL generica (degradacao graciosa).
    ok = open_url(url)
    notify("Handoff: midia", url)
    return ok


def handle_url(dados: dict, config: dict) -> bool:
    url = dados.get("url", "")
    ok = open_url(url)
    notify("Handoff: link", url)
    return ok


def handle_pasta(dados: dict, config: dict) -> bool:
    win = map_android_to_windows(dados.get("caminho", ""), config)
    ok = open_path(win)
    notify("Handoff: pasta", win)
    return ok


def handle_arquivo(dados: dict, config: dict) -> bool:
    win = map_android_to_windows(dados.get("caminho", ""), config)
    ok = open_path(win)
    notify("Handoff: arquivo", win)
    return ok


def handle_texto(dados: dict, config: dict) -> bool:
    texto = dados.get("conteudo", "")
    ok = set_clipboard(texto)
    preview = (texto[:40] + "...") if len(texto) > 40 else texto
    notify("Handoff: texto", f"Copiado para o clipboard: {preview}")
    return ok


def handle_mapa(dados: dict, config: dict) -> bool:
    """mapa: coordenadas (lat/lng) ou query de lugar -> Google Maps no navegador."""
    lat = dados.get("lat")
    lng = dados.get("lng")
    query = dados.get("query") or dados.get("place")
    if lat is not None and lng is not None:
        url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    elif query:
        url = f"https://www.google.com/maps/search/?api=1&query={quote(str(query))}"
    elif dados.get("url"):
        url = dados["url"]
    else:
        logging.warning("mapa sem coordenadas/query/url.")
        return False
    ok = open_url(url)
    notify("Handoff: mapa", url)
    return ok


def handle_contato(dados: dict, config: dict) -> bool:
    """contato: sem app equivalente curado -> joga os dados no clipboard."""
    texto = dados.get("vcard") or json.dumps(dados, ensure_ascii=False)
    ok = set_clipboard(texto)
    notify("Handoff: contato", "Dados do contato copiados para o clipboard")
    return ok


# Tabela curada tipo -> handler.
HANDLERS = {
    "midia": handle_midia,
    "url": handle_url,
    "pasta": handle_pasta,
    "arquivo": handle_arquivo,
    "texto": handle_texto,
    "mapa": handle_mapa,
    "contato": handle_contato,
}


def resolve_descriptor(desc: dict, config: dict) -> bool:
    """Resolve um descritor pela tabela curada + fallback automatico."""
    tipo = (desc.get("tipo") or "").lower()
    dados = desc.get("dados") or {}
    logging.info(f"Descritor tipo={tipo!r} app_origem={desc.get('app_origem')!r}")

    handler = HANDLERS.get(tipo)
    if handler:
        return handler(dados, config)

    # ---- Fallback automatico (PLANO.md secao 4: regras automaticas) ----
    url = dados.get("url", "")
    if url.startswith("http://") or url.startswith("https://"):
        notify("Handoff: link (fallback)", url)
        return open_url(url)
    caminho = dados.get("caminho", "")
    if caminho:
        win = map_android_to_windows(caminho, config)
        notify("Handoff: caminho (fallback)", win)
        return open_path(win)
    logging.warning(f"Tipo desconhecido e sem fallback aplicavel: {desc!r}")
    notify("Handoff: ignorado", f"tipo desconhecido: {tipo!r}")
    return False


def process_line(line: str, config: dict) -> bool:
    """Processa uma linha recebida: descritor JSON ou (compat) URL pura."""
    line = (line or "").strip()
    if not line:
        return False
    if line[0] in "{[":
        try:
            desc = json.loads(line)
        except json.JSONDecodeError as e:
            logging.error(f"JSON invalido: {e} -- linha: {line[:120]!r}")
            return False
        if isinstance(desc, dict):
            return resolve_descriptor(desc, config)
        logging.error(f"Descritor nao e objeto JSON: {type(desc)}")
        return False
    # Compatibilidade: linha simples = URL pura (comportamento antigo).
    return open_url(line)


# --------------------------------------------------------------------------- #
# Modos de operacao                                                            #
# --------------------------------------------------------------------------- #
def collect_payload() -> str:
    """Junta o descritor de argumentos posicionais e/ou do stdin (se encanado)."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    payload = " ".join(args).strip()
    if not payload and not sys.stdin.isatty():
        payload = sys.stdin.read().strip()
    return payload


def once_mode(config: dict) -> int:
    """Executa o descritor DIRETAMENTE neste processo.

    AVISO: se chamado de uma sessao SSH (sshd = sessao 0), a UI abre numa area
    de trabalho NAO visivel (lecao da secao 3 do PLANO). Para handoff real, use
    --send para entregar ao daemon que roda na sessao interativa do usuario.
    """
    payload = collect_payload()
    if not payload:
        print("Nada para processar (descritor vazio).", file=sys.stderr)
        return 1
    ok = process_line(payload, config)
    return 0 if ok else 1


def send_mode() -> int:
    """Encaminha o descritor ao daemon local (sessao interativa do usuario)."""
    payload = collect_payload()
    if not payload:
        print("Nada para enviar (descritor vazio).", file=sys.stderr)
        return 1
    try:
        sock = socket.create_connection((DAEMON_HOST, DAEMON_PORT), timeout=3)
    except OSError as e:
        msg = (f"Daemon nao esta rodando em {DAEMON_HOST}:{DAEMON_PORT} ({e}). "
               f"Inicie-o com: pythonw agente.py --daemon (ou start-agente.vbs).")
        logging.error(msg)
        print(msg, file=sys.stderr)
        return 1
    with sock:
        # Garante uma unica linha (o protocolo e 1 descritor por linha).
        sock.sendall((payload.replace("\n", " ").strip() + "\n").encode("utf-8"))
    logging.info(f"SEND -> daemon: {payload[:160]}")
    return 0


def daemon_loop(config: dict):
    """Escuta TCP local e resolve cada descritor recebido (1 por linha)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((DAEMON_HOST, DAEMON_PORT))
    except OSError as e:
        logging.info(f"Bind falhou ({e}); daemon provavelmente ja ativo. Saindo.")
        print(f"Agente ja parece estar rodando em {DAEMON_HOST}:{DAEMON_PORT}.")
        return
    srv.listen(5)
    logging.info(f"Agente ouvindo em {DAEMON_HOST}:{DAEMON_PORT}")
    print(f"Agente Ecossistema ouvindo em {DAEMON_HOST}:{DAEMON_PORT}", flush=True)
    notify("Ecossistema", "Agente ativo na sua sessao")
    try:
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    data = conn.recv(65536).decode("utf-8", "replace")
                    for line in data.splitlines():
                        process_line(line, config)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Erro no daemon: {e}")
    finally:
        srv.close()


def main() -> int:
    setup_logging()
    config = load_config()
    if "--daemon" in sys.argv:
        logging.info("Daemon iniciado")
        daemon_loop(config)
        return 0
    if "--send" in sys.argv:
        return send_mode()
    if "--once" in sys.argv:
        return once_mode(config)
    # Sem modo: por seguranca, padrao = --send (entrega ao daemon, sessao do usuario).
    print("Nenhum modo informado; usando --send (entrega ao daemon).",
          file=sys.stderr)
    return send_mode()


if __name__ == "__main__":
    sys.exit(main())
