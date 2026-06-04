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
    python agente.py --serve           # CANAL PERSISTENTE: relay stdin<->daemon (sessao 0/sshd)
    python agente.py --send            # le 1 descritor (JSON) do stdin e envia ao daemon
    python agente.py --send '<json>'   # idem, descritor como argumento
    python agente.py --once '<json>'   # executa direto neste processo (debug; ver aviso)

CANAL PERSISTENTE (MELHORIAS_APPLE.md proposta A): em vez de abrir uma sessao SSH
por evento (--send), o app mantem UMA sessao viva rodando `agente.py --serve`. O
--serve e um RELAY burro: tudo que chega na stdin (do celular, via SSH) e repassado
ao daemon local; tudo que o daemon devolve volta pela stdout (ao celular). Toda a
logica (abrir UI, presenca, PC->Android) fica no daemon -- na sessao do usuario --,
preservando a licao da Sessao 0/1: o --serve (sessao 0) NUNCA abre UI.

Protocolo de controle (linhas JSON com a chave "_ctrl", para nao colidir com os
descritores que usam "tipo"):
    celular->daemon: {"_ctrl":"hello","device":"s24fe","name":"S24 FE"}
                     {"_ctrl":"ping"}
                     {"_ctrl":"activity","texto":"YouTube"}
    daemon->celular: {"_ctrl":"pong"}
                     {"_ctrl":"ack","ok":true}
                     {"_ctrl":"push","desc":{...descritor PC->Android...}}

Compatibilidade: se a linha recebida NAO for JSON, e tratada como URL pura
(comportamento antigo do receiver.py). O --send segue funcionando (fallback).

Config: <pasta-do-script>/config.json (ver config.example.json).
Log:    <home>/.handoff/agente.log
"""
import sys
import os
import json
import time
import socket
import logging
import threading
import webbrowser
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

HANDOFF_DIR = Path.home() / ".handoff"
LOG_FILE = HANDOFF_DIR / "agente.log"

# FROZEN = rodando como .exe empacotado (PyInstaller). Nesse caso __file__ aponta
# para uma pasta temporaria; a base estavel e a pasta do proprio executavel.
FROZEN = getattr(sys, "frozen", False)
APP_DIR = (
    Path(sys.executable).resolve().parent if FROZEN
    else Path(__file__).resolve().parent
)

DAEMON_HOST = os.environ.get("HANDOFF_HOST", "127.0.0.1")
DAEMON_PORT = int(os.environ.get("HANDOFF_PORT", "8765"))

IS_WINDOWS = os.name == "nt"

# --------------------------------------------------------------------------- #
# Estado compartilhado do canal persistente (proposta A)                       #
#                                                                              #
# Vive no processo do DAEMON (sessao do usuario). A UI do PC (painel.py) roda  #
# no mesmo processo, entao le este estado direto (sem IPC). PRESENCA = quem    #
# esta online; SERVE_CONNS = sockets dos relays --serve ativos, usados para    #
# EMPURRAR eventos PC->Android (proposta E) de volta ao celular certo.         #
# --------------------------------------------------------------------------- #
_STATE_LOCK = threading.Lock()
PRESENCA: dict = {}      # device_id -> {"name", "online", "last_seen", "atividade"}
SERVE_CONNS: dict = {}   # device_id -> socket (relay --serve vivo)


def _agora() -> float:
    return time.time()


def presenca_marcar(device_id: str, **campos):
    """Atualiza o estado de presenca de um dispositivo (thread-safe)."""
    if not device_id:
        return
    with _STATE_LOCK:
        dev = PRESENCA.setdefault(
            device_id, {"name": device_id, "online": False, "last_seen": 0.0, "atividade": ""}
        )
        dev.update(campos)
        dev["last_seen"] = _agora()


def presenca_snapshot() -> list:
    """Lista de dispositivos para a UI (copia segura)."""
    with _STATE_LOCK:
        return [dict(id=k, **v) for k, v in PRESENCA.items()]


def push_para_dispositivo(device_id: str, descritor: dict) -> bool:
    """Empurra um descritor PC->Android pelo relay --serve do dispositivo.

    Usado pela aba 'Acoes rapidas' da UI (proposta E). Retorna False se o
    dispositivo nao tiver um canal persistente vivo agora.
    """
    with _STATE_LOCK:
        conn = SERVE_CONNS.get(device_id)
    if conn is None:
        logging.info(f"push falhou: {device_id!r} sem canal persistente vivo.")
        return False
    try:
        linha = json.dumps({"_ctrl": "push", "desc": descritor}, ensure_ascii=False) + "\n"
        conn.sendall(linha.encode("utf-8"))
        return True
    except OSError as e:
        logging.warning(f"push erro p/ {device_id!r}: {e}")
        return False


def resolve_config_file() -> Path:
    """Acha o config.json num local estavel (funciona tambem empacotado).

    Ordem: ao lado do exe/script -> %APPDATA%/Ecossistema/config.json (so frozen).
    Em dev (nao empacotado) usa sempre a pasta do script.
    """
    local = APP_DIR / "config.json"
    if local.exists() or not FROZEN:
        return local
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Ecossistema" / "config.json"
    return local


def hide_console_window():
    """No exe empacotado (console), esconde a janela ao virar daemon — assim o
    auto-start nao deixa um terminal aberto, mas --send/--list-apps continuam
    com stdout/stdin normais (necessario para o SSH)."""
    if not (IS_WINDOWS and FROZEN):
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass

# Roda como daemon sob pythonw (sem console). Spawnar apps de console (powershell
# do toast, clip.exe, explorer) faria o Windows ALOCAR um console novo -> uma
# janela de terminal pisca na tela. CREATE_NO_WINDOW impede isso.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


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
        with open(resolve_config_file(), "r", encoding="utf-8") as fh:
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
            creationflags=CREATE_NO_WINDOW,
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
                subprocess.Popen(["explorer.exe", str(p)], creationflags=CREATE_NO_WINDOW)
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
        proc = subprocess.run(
            cmd, input=texto.encode("utf-8"), check=False,
            creationflags=CREATE_NO_WINDOW,
        )
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


def handle_app(dados: dict, config: dict) -> bool:
    """app: abre um programa do PC (atalho .lnk/.url do Menu Iniciar)."""
    caminho = dados.get("caminho", "")
    nome = dados.get("nome") or caminho
    ok = open_path(caminho)
    notify("Handoff: app", str(nome))
    return ok


def handle_abrir_arquivo(dados: dict, config: dict) -> bool:
    """abrir_arquivo: abre no PC (app padrao) um arquivo recebido por SFTP.

    `rel` e um caminho relativo ao HOME do usuario (ex.: "Ecossistema/foto.jpg"),
    que e exatamente onde o app sobe o arquivo via SFTP (raiz = home no Windows).
    """
    rel = (dados.get("rel") or dados.get("caminho") or "").strip()
    if not rel:
        return False
    p = Path(rel) if os.path.isabs(rel) else (Path.home() / rel.replace("/", os.sep))
    ok = open_path(str(p))  # os.startfile -> abre no app padrao
    notify("Handoff: arquivo recebido", p.name)
    return ok


def list_apps() -> list:
    """Lista apps do PC pelos atalhos do Menu Iniciar (.lnk/.url), sem duplicar."""
    if not IS_WINDOWS:
        return []
    bases = []
    pd = os.environ.get("ProgramData")
    ad = os.environ.get("APPDATA")
    if pd:
        bases.append(os.path.join(pd, "Microsoft", "Windows", "Start Menu", "Programs"))
    if ad:
        bases.append(os.path.join(ad, "Microsoft", "Windows", "Start Menu", "Programs"))
    vistos = {}
    for base in bases:
        if not os.path.isdir(base):
            continue
        for raiz, _dirs, arquivos in os.walk(base):
            for arq in arquivos:
                low = arq.lower()
                if not (low.endswith(".lnk") or low.endswith(".url")):
                    continue
                nome = os.path.splitext(arq)[0]
                if "uninstall" in nome.lower() or "desinstal" in nome.lower():
                    continue
                chave = nome.lower()
                if chave not in vistos:
                    vistos[chave] = {"nome": nome, "caminho": os.path.join(raiz, arq)}
    return sorted(vistos.values(), key=lambda a: a["nome"].lower())


# Tabela curada tipo -> handler.
HANDLERS = {
    "midia": handle_midia,
    "url": handle_url,
    "pasta": handle_pasta,
    "arquivo": handle_arquivo,
    "texto": handle_texto,
    "mapa": handle_mapa,
    "contato": handle_contato,
    "app": handle_app,
    "abrir_arquivo": handle_abrir_arquivo,
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


def _handle_ctrl(msg: dict, conn: socket.socket, device_box: list) -> None:
    """Trata uma mensagem de controle (_ctrl) vinda de um relay --serve.

    device_box e uma lista de 1 posicao usada como referencia mutavel para o
    id do dispositivo desta conexao (descoberto no 'hello'), de modo que a
    limpeza no fim consiga desregistrar o socket.
    """
    ctrl = msg.get("_ctrl")
    if ctrl == "hello":
        device_id = str(msg.get("device") or "desconhecido")
        device_box[0] = device_id
        with _STATE_LOCK:
            anterior = SERVE_CONNS.get(device_id)
            SERVE_CONNS[device_id] = conn
        # Se ja existia um canal para este device (reconexao apos o Wi-Fi cair,
        # com o TCP antigo ainda "vivo" no PC por nao ter recebido FIN/RST),
        # derruba o zumbi agora para nao acumular conexao/thread orfas. O finally
        # daquela conexao vera que ela nao e mais a vigente e nao marcara offline.
        if anterior is not None and anterior is not conn:
            try:
                anterior.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                anterior.close()
            except OSError:
                pass
            logging.info(f"Canal anterior derrubado na reconexao: {device_id}")
        presenca_marcar(device_id, name=str(msg.get("name") or device_id), online=True)
        logging.info(f"Canal persistente ON: {device_id}")
        _responder(conn, {"_ctrl": "ack", "ok": True})
    elif ctrl == "ping":
        if device_box[0]:
            presenca_marcar(device_box[0], online=True)
        _responder(conn, {"_ctrl": "pong"})
    elif ctrl == "activity":
        if device_box[0]:
            presenca_marcar(device_box[0], online=True, atividade=str(msg.get("texto") or ""))
    else:
        logging.debug(f"_ctrl desconhecido ignorado: {ctrl!r}")


def _responder(conn: socket.socket, msg: dict) -> None:
    try:
        conn.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError as e:
        logging.debug(f"resposta ao canal falhou (ignorado): {e}")


def _handle_connection(conn: socket.socket, config: dict) -> None:
    """Atende UMA conexao local. Funciona tanto para o --send (envia 1 linha e
    fecha) quanto para o --serve (fica vivo, bidirecional). Le linha-a-linha
    ate o outro lado fechar."""
    device_box = [None]
    try:
        f = conn.makefile("rb")
        for raw in f:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if line[0] == "{":
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON invalido no canal: {e} -- {line[:120]!r}")
                    continue
                if isinstance(obj, dict) and "_ctrl" in obj:
                    _handle_ctrl(obj, conn, device_box)
                    continue
            # Descritor normal (ou URL pura): resolve e abre a UI nesta sessao.
            process_line(line, config)
    except Exception as e:
        logging.error(f"Erro na conexao: {e}")
    finally:
        dev = device_box[0]
        if dev:
            ainda_atual = False
            with _STATE_LOCK:
                if SERVE_CONNS.get(dev) is conn:
                    SERVE_CONNS.pop(dev, None)
                    ainda_atual = True
            # So marca offline/loga OFF se ESTA conexao ainda era a vigente do
            # device. Uma conexao antiga (substituida por uma reconexao, ex.: o
            # Wi-Fi caiu e o TCP velho ficou zumbi) NAO deve marcar o device
            # offline — ele segue online pela conexao nova.
            if ainda_atual:
                presenca_marcar(dev, online=False)
                logging.info(f"Canal persistente OFF: {dev}")
            else:
                logging.info(f"Canal antigo descartado (reconexao): {dev}")
        try:
            conn.close()
        except OSError:
            pass


def daemon_loop(config: dict):
    """Escuta TCP local; uma thread por conexao (suporta --send e --serve)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((DAEMON_HOST, DAEMON_PORT))
    except OSError as e:
        logging.info(f"Bind falhou ({e}); daemon provavelmente ja ativo. Saindo.")
        print(f"Agente ja parece estar rodando em {DAEMON_HOST}:{DAEMON_PORT}.")
        return
    srv.listen(8)
    logging.info(f"Agente ouvindo em {DAEMON_HOST}:{DAEMON_PORT}")
    print(f"Agente Ecossistema ouvindo em {DAEMON_HOST}:{DAEMON_PORT}", flush=True)
    notify("Ecossistema", "Agente ativo na sua sessao")
    try:
        while True:
            try:
                conn, _ = srv.accept()
                threading.Thread(
                    target=_handle_connection, args=(conn, config), daemon=True
                ).start()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Erro ao aceitar conexao: {e}")
    finally:
        srv.close()


def serve_mode() -> int:
    """CANAL PERSISTENTE (proposta A): relay bidirecional stdin<->daemon.

    Roda na sessao do sshd (sessao 0). NAO abre UI -- so encaminha. Tudo da
    stdin (celular) vai ao daemon; tudo do daemon volta pela stdout (celular).
    Sai quando qualquer lado fecha, para o app reconectar com backoff.
    """
    try:
        sock = socket.create_connection((DAEMON_HOST, DAEMON_PORT), timeout=3)
        # create_connection deixa o timeout do connect (3s) GRUDADO no socket.
        # O relay precisa ser BLOQUEANTE: sem isso, a leitura do daemon estoura
        # socket.timeout apos 3s ociosos, a bomba morre e o canal cai a cada 3s
        # (o 1o heartbeat so vem aos 20s, nunca a tempo). settimeout(None) = blocking.
        sock.settimeout(None)
    except OSError as e:
        msg = (f"Daemon nao esta rodando em {DAEMON_HOST}:{DAEMON_PORT} ({e}). "
               f"Inicie-o com: pythonw agente.py --daemon (ou start-agente.vbs).")
        logging.error(msg)
        print(msg, file=sys.stderr)
        return 1

    parar = threading.Event()

    def bombeia_entrada():
        """celular (stdin) -> daemon. Ao acabar a stdin (EOF), faz meio-fecho do
        socket (SHUT_WR) mas NAO encerra o relay: continua drenando a saida ate o
        daemon encerrar — assim respostas em transito (ack/pong/push) nao se perdem."""
        try:
            for raw in sys.stdin.buffer:
                if not raw.endswith(b"\n"):
                    raw += b"\n"
                sock.sendall(raw)
        except Exception as e:
            logging.debug(f"serve entrada encerrada: {e}")
        finally:
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def bombeia_saida():
        """daemon -> celular (stdout). O fim DESTA bomba (daemon/SSH fechou) e o
        que encerra o relay."""
        try:
            f = sock.makefile("rb")
            for raw in f:
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
        except Exception as e:
            logging.debug(f"serve saida encerrada: {e}")
        finally:
            parar.set()

    t_in = threading.Thread(target=bombeia_entrada, daemon=True)
    t_out = threading.Thread(target=bombeia_saida, daemon=True)
    t_in.start()
    t_out.start()
    parar.wait()
    try:
        sock.close()
    except OSError:
        pass
    return 0


def pair_info_mode() -> int:
    """Imprime a info do QR (JSON) no stdout. Usado pela UI do PC (painel.py)."""
    import pareamento
    info = pareamento.monta_info(port=int(os.environ.get("HANDOFF_SSH_PORT", "22")))
    print(json.dumps(info, ensure_ascii=False))
    return 0


def pair_mode() -> int:
    """Modo CLI de pareamento: mostra a info + QR (ASCII) e abre o canal."""
    import pareamento
    info = pareamento.monta_info(port=int(os.environ.get("HANDOFF_SSH_PORT", "22")))
    texto = pareamento.info_para_qr_texto(info)
    print("==> Emparelhamento por QR")
    print(f"    host={info.get('host')} port={info.get('port')} user={info.get('user')}")
    print(f"    fingerprint={info.get('fp')}")
    print(f"    token={info.get('token')} pair_port={info.get('pair_port')}")
    ascii_qr = pareamento.render_qr_ascii(texto)
    if ascii_qr:
        print(ascii_qr)
    else:
        print("    (instale 'qrcode' para ver o QR; conteudo abaixo)")
        print("   ", texto)
    print("    Escaneie no app do celular. Aguardando...")
    res = pareamento.servir_pareamento(info)
    if res:
        print(f"    OK: pareado com {res.get('name')}.")
        return 0
    print("    Pareamento expirou sem dispositivo.", file=sys.stderr)
    return 1


def main() -> int:
    # stdout/err em UTF-8: o console do Windows e cp1252 e quebraria ao imprimir
    # o QR (blocos unicode) ou JSON com acentos/emoji (UnicodeEncodeError). Tambem
    # garante que --list-apps saia correto pelo SSH.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    setup_logging()
    config = load_config()
    if "--list-apps" in sys.argv:
        # Lista os apps do PC em JSON no stdout (o celular le isso via SSH).
        print(json.dumps(list_apps(), ensure_ascii=False))
        return 0
    if "--pair-info" in sys.argv:
        return pair_info_mode()
    if "--pair" in sys.argv:
        return pair_mode()
    if "--daemon" in sys.argv:
        logging.info("Daemon iniciado")
        hide_console_window()
        daemon_loop(config)
        return 0
    if "--serve" in sys.argv:
        return serve_mode()
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
