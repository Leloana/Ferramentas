"""Monta o index.html a partir dos parciais em `client/partials/`.

O front fica dividido por tela (um arquivo por modal/área), mas o navegador
recebe uma página só, já montada: TVs antigas carregam tudo numa requisição e
continuam sem build step. Marcador aceito no HTML:

    <!-- @include partials/header.html -->

O caminho é relativo a `client/` e não pode sair dela. Parciais podem incluir
outros parciais (até `MAX_DEPTH` níveis).
"""
from __future__ import annotations

import re
from pathlib import Path

INCLUDE_RE = re.compile(r"<!--\s*@include\s+([\w./-]+)\s*-->")
MAX_DEPTH = 4


class IncludeError(RuntimeError):
    pass


def _resolve(client_dir: Path, rel: str) -> Path:
    path = (client_dir / rel).resolve()
    if client_dir.resolve() not in path.parents:
        raise IncludeError(f"include fora de client/: {rel}")
    if not path.is_file():
        raise IncludeError(f"include não encontrado: {rel}")
    return path


def render_includes(text: str, client_dir: Path, depth: int = 0) -> str:
    if depth > MAX_DEPTH:
        raise IncludeError("includes aninhados demais (ciclo?)")

    def replace(match: re.Match) -> str:
        path = _resolve(client_dir, match.group(1))
        return render_includes(path.read_text(encoding="utf-8"), client_dir, depth + 1)

    return INCLUDE_RE.sub(replace, text)


def render_page(client_dir: Path, page: str = "index.html") -> str:
    return render_includes((client_dir / page).read_text(encoding="utf-8"), client_dir)
