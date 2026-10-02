"""Lê `karaoke/.env` (chaves locais, fora do git) para os.environ.

Sem dependência nova: linhas `NOME=valor`, `#` comenta. Variável que já existe no
ambiente ganha (o .env só completa). Valor vazio não é carregado.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_loaded = False


def load_env_file(path: Path = ENV_FILE) -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
