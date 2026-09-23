import hashlib
import hmac
import ipaddress
import secrets
import time
from typing import Optional
from fastapi import Request, HTTPException, status, WebSocket
from config import load_config

COOKIE_NAME = "agent_remote_session"
SESSION_DURATION_SECONDS = 7 * 24 * 3600  # 7 dias


def _get_secret() -> bytes:
    cfg = load_config()
    secret = cfg.get("server", {}).get("session_secret", "fallback_secret_key_123")
    return secret.encode("utf-8")


def get_client_ip(request: Request) -> str:
    """Extrai o IP real do cliente considerando Cloudflare Tunnel e proxies reversos."""
    # 1. Header oficial da Cloudflare (IP do visitante)
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # 2. X-Forwarded-For
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()

    # 3. X-Real-IP
    x_real = request.headers.get("X-Real-IP")
    if x_real:
        return x_real.strip()

    # 4. Fallback para conexão de socket direto
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def get_ws_client_ip(websocket: WebSocket) -> str:
    """Extrai o IP real do cliente em conexões WebSocket."""
    cf_ip = websocket.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    xff = websocket.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    x_real = websocket.headers.get("X-Real-IP")
    if x_real:
        return x_real.strip()
    if websocket.client and websocket.client.host:
        return websocket.client.host
    return "127.0.0.1"


def is_ip_allowed(client_ip_str: str) -> bool:
    """Verifica se o IP informado está autorizado na whitelist."""
    cfg = load_config()
    server_cfg = cfg.get("server", {})
    if not server_cfg.get("ip_whitelist_enabled", False):
        return True  # Whitelist desativada: todos os IPs permitidos

    allowed_list = server_cfg.get("ip_whitelist", [])
    if not allowed_list:
        return True

    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        return False

    for item in allowed_list:
        try:
            if "/" in item:
                net = ipaddress.ip_network(item, strict=False)
                if client_ip in net:
                    return True
            else:
                if client_ip == ipaddress.ip_address(item):
                    return True
        except ValueError:
            continue
    return False


def check_ip_whitelist(request: Request) -> bool:
    """Lança HTTP 403 Forbidden se o IP do cliente não estiver na whitelist."""
    client_ip = get_client_ip(request)
    if not is_ip_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado: seu IP ({client_ip}) não está na whitelist autorizada do servidor."
        )
    return True


def verify_password(plain_password: str) -> bool:
    """Verifica a senha informada contra a configurada usando compare_digest."""
    cfg = load_config()
    expected = cfg.get("server", {}).get("password", "")
    if not expected:
        return True  # Sem senha definida = liberado
    return secrets.compare_digest(plain_password.strip(), expected.strip())


def create_session_token() -> str:
    """Cria um token assinado HMAC no formato 'timestamp.assinatura'."""
    timestamp = str(int(time.time()))
    secret = _get_secret()
    sig = hmac.new(secret, timestamp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{timestamp}.{sig}"


def verify_session_token(token: Optional[str]) -> bool:
    """Verifica a integridade e expiração do token de sessão."""
    if not token or "." not in token:
        return False
    try:
        timestamp_str, sig = token.split(".", 1)
        timestamp = int(timestamp_str)
        # Verifica se expirou
        if time.time() - timestamp > SESSION_DURATION_SECONDS:
            return False
        # Verifica assinatura
        secret = _get_secret()
        expected_sig = hmac.new(secret, timestamp_str.encode("utf-8"), hashlib.sha256).hexdigest()
        return secrets.compare_digest(sig, expected_sig)
    except Exception:
        return False


def require_auth(request: Request) -> bool:
    """Dependência para endpoints HTTP que exigem login e verificação de IP."""
    check_ip_whitelist(request)

    token = request.cookies.get(COOKIE_NAME)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:].strip()
        if verify_session_token(bearer_token):
            return True

    custom_pwd = request.headers.get("X-Password")
    if custom_pwd and verify_password(custom_pwd):
        return True

    if not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária"
        )
    return True


def is_authenticated(request: Request) -> bool:
    """Retorna True se a requisição estiver autenticada, False caso contrário."""
    token = request.cookies.get(COOKIE_NAME)
    return verify_session_token(token)


async def verify_ws_auth(websocket: WebSocket) -> bool:
    """Verifica IP e autenticação em conexões WebSocket."""
    client_ip = get_ws_client_ip(websocket)
    if not is_ip_allowed(client_ip):
        return False

    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        token = websocket.query_params.get("token")
    return verify_session_token(token)
