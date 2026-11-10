"""Sobe a API na rede local e mostra o que digitar no celular."""
from __future__ import annotations

import socket

import uvicorn

import config
from app import token


def ip_local() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.0.1", 1))  # não envia nada; só escolhe a interface da LAN
        return s.getsockname()[0]
    finally:
        s.close()


if __name__ == "__main__":
    print("=" * 52, flush=True)
    print(f"  Endereço no app : http://{ip_local()}:{config.PORTA}")
    print(f"  Token do aparelho: {token()}")
    print("=" * 52, flush=True)
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORTA, log_level="info")
