"""Sandbox de sistema de arquivos: restringe ferramentas a diretórios permitidos.

Guardrail obrigatório (PLANO.md secão 7.5): ferramentas que tocam o sistema de
arquivos não podem escapar dos diretórios whitelistados via path traversal,
symlinks, ou caminhos absolutos fora do escopo.
"""
from __future__ import annotations

from pathlib import Path


class SandboxViolation(Exception):
    """Levantado quando um caminho solicitado cai fora dos diretórios permitidos."""


def resolve_within_sandbox(raw_path: str, allowed_dirs: list[Path]) -> Path:
    """Resolve `raw_path` e garante que ele esteja dentro de algum diretório permitido.

    Resolve symlinks e `..` antes de comparar, para que truques de path traversal
    não escapem do sandbox.
    """
    if not allowed_dirs:
        raise SandboxViolation("Nenhum diretório permitido configurado.")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        # caminho relativo é resolvido a partir do primeiro diretório permitido
        candidate = allowed_dirs[0] / candidate

    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise SandboxViolation(f"Caminho inválido: {raw_path!r} ({exc})") from exc

    for allowed in allowed_dirs:
        try:
            resolved.relative_to(allowed)
            return resolved
        except ValueError:
            continue

    raise SandboxViolation(
        f"Caminho {raw_path!r} está fora dos diretórios permitidos: "
        f"{[str(d) for d in allowed_dirs]}"
    )
