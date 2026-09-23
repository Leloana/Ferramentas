import hashlib
import hmac
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
    """Dependência para endpoints HTTP que exigem login."""
    token = request.cookies.get(COOKIE_NAME)
    # Também aceita header Authorization: Bearer <token> ou X-Password
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
    """Verifica autenticação em conexões WebSocket (cookie ou query param ?token=)."""
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        token = websocket.query_params.get("token")
    return verify_session_token(token)
