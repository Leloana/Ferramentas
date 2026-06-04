#!/usr/bin/env python3
"""
pareamento.py  --  Emparelhamento por QR do Ecossistema (MELHORIAS_APPLE.md B).

Em vez de digitar IP/porta e COLAR a chave PEM na mao, o PC mostra um QR com
{host, porta, fingerprint da host key, token}. O celular escaneia, gera o par
de chaves localmente e registra a PUBLICA no PC por um canal de pareamento
efetivo por poucos segundos (token-gated). Bonus de seguranca: o fingerprint vai
no QR -> o app FIXA (pinning) e elimina o PromiscuousVerifier.

Fluxo (lado PC):
  1. monta_info()      -> dict {host, tshost, port, user, fp, token, pair_port}
  2. servir_pareamento(info) -> abre um listener TCP token-gated por `timeout` s;
     quando o celular manda {token, pubkey, name}, valida o token e autoriza a
     chave (autorizar_chave) -> administrators_authorized_keys (com elevacao UAC).

Sem dependencias para o nucleo. O QR (qrcode) e opcional e importado sob demanda.
"""
import os
import sys
import json
import time
import base64
import socket
import hashlib
import logging
import secrets
import subprocess
from pathlib import Path

IS_WINDOWS = os.name == "nt"
PAIR_PORT_PADRAO = 8766
PAIR_TIMEOUT_PADRAO = 180  # segundos da janela de pareamento

# Pasta de dados do OpenSSH no Windows (host keys). Em dev (Linux) cai para ~/.ssh.
SSH_DATA_DIR = (
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ssh" if IS_WINDOWS
    else Path.home() / ".ssh"
)


# --------------------------------------------------------------------------- #
# Fingerprint da host key (formato "SHA256:..." identico ao ssh-keygen -lf)    #
# --------------------------------------------------------------------------- #
def _fingerprint_de_pub(linha_pub: str):
    """Calcula 'SHA256:<base64>' a partir de uma linha de chave publica OpenSSH
    ('<tipo> <base64blob> [comentario]'). Igual ao que o ssh-keygen mostra."""
    partes = (linha_pub or "").split()
    if len(partes) < 2:
        return None
    try:
        blob = base64.b64decode(partes[1])
    except Exception:
        return None
    digest = hashlib.sha256(blob).digest()
    b64 = base64.b64encode(digest).decode("ascii").rstrip("=")
    return "SHA256:" + b64


def _fingerprint_via_keyscan(port: int = 22, host: str = "127.0.0.1"):
    """Fingerprint da host key via 'ssh-keyscan' — pega a chave pela REDE, sem
    ler arquivo nem admin. No Windows a ACL de ProgramData\\ssh nega a leitura da
    .pub ao usuario, entao este e o caminho confiavel quando o agente roda sem
    elevacao."""
    try:
        out = subprocess.run(
            ["ssh-keyscan", "-t", "ed25519", "-p", str(port), host],
            capture_output=True, text=True, timeout=6,
        )
    except Exception as e:
        logging.debug(f"ssh-keyscan falhou: {e}")
        return None
    for linha in (out.stdout or "").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split()  # "<host> <tipo> <base64>"
        if len(partes) >= 3 and partes[1].startswith("ssh-"):
            fp = _fingerprint_de_pub(partes[1] + " " + partes[2])
            if fp:
                return fp
    return None


def host_key_fingerprint(ssh_dir: Path = None, port: int = 22):
    """Fingerprint da host key do sshd (prefere ed25519). None se nao achar.

    1) tenta ler a .pub localmente; 2) se nao der (ACL/arquivo), cai para o
    ssh-keyscan na porta do sshd (funciona sem admin)."""
    ssh_dir = ssh_dir or SSH_DATA_DIR
    for nome in ("ssh_host_ed25519_key.pub", "ssh_host_ecdsa_key.pub", "ssh_host_rsa_key.pub"):
        p = ssh_dir / nome
        if p.exists():
            try:
                fp = _fingerprint_de_pub(p.read_text(encoding="utf-8", errors="replace"))
                if fp:
                    return fp
            except Exception as e:
                logging.debug(f"falha lendo host key {p}: {e}")
    fp = _fingerprint_via_keyscan(port)
    if fp:
        return fp
    logging.warning(f"Host key nao encontrada (arquivos em {ssh_dir} nem via ssh-keyscan)")
    return None


# --------------------------------------------------------------------------- #
# Descoberta de IPs (LAN e Tailscale)                                          #
# --------------------------------------------------------------------------- #
def lan_ip():
    """IP da LAN (best-effort): abre um socket UDP 'para fora' e le o IP local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def tailscale_ip():
    """IP 100.x do Tailscale, se disponivel (best-effort via `tailscale ip -4`)."""
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=4,
        )
        ip = (out.stdout or "").strip().splitlines()
        return ip[0].strip() if ip else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Montagem da info do QR                                                        #
# --------------------------------------------------------------------------- #
def gerar_token() -> str:
    return secrets.token_urlsafe(18)


def monta_info(port: int = 22, user: str = None, ssh_dir: Path = None) -> dict:
    """Monta o dicionario que vai dentro do QR (e que a UI desenha)."""
    user = user or os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return {
        "v": 1,                      # versao do protocolo de pareamento
        "host": lan_ip(),            # IP da LAN
        "tshost": tailscale_ip(),    # IP Tailscale (pode ser None)
        "port": int(port),
        "user": user,
        "fp": host_key_fingerprint(ssh_dir, int(port)),
        "token": gerar_token(),
        "pair_port": PAIR_PORT_PADRAO,
    }


def info_para_qr_texto(info: dict) -> str:
    """Serializa a info para o conteudo do QR (JSON compacto, 1 linha)."""
    return json.dumps(info, ensure_ascii=False, separators=(",", ":"))


def render_qr_ascii(texto: str) -> str:
    """QR em ASCII para o terminal (fallback sem a UI). Vazio se sem a lib."""
    try:
        import qrcode  # opcional
    except Exception:
        return ""
    qr = qrcode.QRCode(border=1)
    qr.add_data(texto)
    qr.make(fit=True)
    import io
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Autorizacao da chave publica (escreve no authorized_keys)                    #
# --------------------------------------------------------------------------- #
def autorizar_chave(pubkey: str) -> bool:
    """Autoriza a chave publica do celular no PC.

    Windows: chama add-authorized-key.ps1 ELEVADO (UAC unico) — escreve em
    administrators_authorized_keys com a ACL correta. Dev (Linux/macOS): grava
    em ~/.ssh/authorized_keys (para testar o fluxo sem o hardware Windows).
    """
    pubkey = (pubkey or "").strip()
    if not pubkey or not pubkey.startswith("ssh-"):
        logging.error(f"Pubkey invalida no pareamento: {pubkey[:40]!r}")
        return False

    if not IS_WINDOWS:
        # Caminho de DEV: authorized_keys do usuario, idempotente.
        ak = Path.home() / ".ssh" / "authorized_keys"
        ak.parent.mkdir(parents=True, exist_ok=True)
        existentes = ak.read_text(encoding="utf-8").splitlines() if ak.exists() else []
        if pubkey not in [l.strip() for l in existentes]:
            with open(ak, "a", encoding="utf-8") as fh:
                fh.write(pubkey + "\n")
        try:
            os.chmod(ak, 0o600)
        except OSError:
            pass
        logging.info(f"[dev] chave autorizada em {ak}")
        return True

    # Windows: escreve a chave num temp e roda o helper ELEVADO.
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent
    script = base / "add-authorized-key.ps1"
    tmp = Path(os.environ.get("TEMP", ".")) / f"ecossistema_pair_{secrets.token_hex(4)}.pub"
    try:
        tmp.write_text(pubkey + "\n", encoding="utf-8")
        # Start-Process -Verb RunAs dispara o UAC uma vez; -Wait para sabermos o fim.
        ps = (
            "Start-Process powershell -Verb RunAs -Wait -ArgumentList "
            "'-NoProfile','-ExecutionPolicy','Bypass','-File',"
            f"'{script}','-PubKeyFile','{tmp}'"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=120,
        )
        ok = proc.returncode == 0
        if not ok:
            logging.error(f"add-authorized-key falhou: {proc.stderr or proc.stdout}")
        return ok
    except Exception as e:
        logging.error(f"Erro autorizando chave (elevacao): {e}")
        return False
    finally:
        # O helper apaga o temp; aqui e so garantia caso a elevacao nem rode.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Listener de pareamento (token-gated, janela curta)                           #
# --------------------------------------------------------------------------- #
def servir_pareamento(info: dict, timeout: int = PAIR_TIMEOUT_PADRAO, on_result=None) -> dict:
    """Abre o canal de pareamento por ate `timeout` s. Retorna o dict do
    dispositivo pareado ({'name','device','pubkey'}) ou {} se expirar.

    Protocolo (1 linha JSON do celular):
        {"token":"...","pubkey":"ssh-ed25519 ...","name":"S24 FE","device":"..."}
    Resposta do PC:
        {"ok":true,"user":"<usuario>"}  |  {"ok":false,"erro":"..."}
    on_result(dict|None) e chamado ao fim (para a UI atualizar).
    """
    token = info.get("token")
    porta = int(info.get("pair_port", PAIR_PORT_PADRAO))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", porta))
    srv.listen(1)
    srv.settimeout(1.0)
    logging.info(f"Pareamento ouvindo em 0.0.0.0:{porta} por {timeout}s")
    fim = time.time() + timeout
    resultado = {}
    try:
        while time.time() < fim:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(10)
                try:
                    linha = conn.makefile("rb").readline().decode("utf-8", "replace").strip()
                    msg = json.loads(linha) if linha else {}
                except Exception as e:
                    logging.warning(f"pareamento: payload invalido ({e})")
                    _resp(conn, {"ok": False, "erro": "payload invalido"})
                    continue
                if not secrets.compare_digest(str(msg.get("token", "")), str(token)):
                    logging.warning("pareamento: token invalido")
                    _resp(conn, {"ok": False, "erro": "token invalido"})
                    continue
                if autorizar_chave(msg.get("pubkey", "")):
                    _resp(conn, {"ok": True, "user": info.get("user", "")})
                    resultado = {
                        "name": msg.get("name") or "Android",
                        "device": msg.get("device") or "",
                        "pubkey": msg.get("pubkey", ""),
                    }
                    logging.info(f"Pareado: {resultado['name']}")
                    break
                _resp(conn, {"ok": False, "erro": "falha ao autorizar a chave"})
    finally:
        srv.close()
        if on_result:
            try:
                on_result(resultado or None)
            except Exception:
                pass
    return resultado


def _resp(conn, obj: dict):
    try:
        conn.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError:
        pass
