"""Pasta de uma música a partir do slug/id vindo da requisição.

O slug chega do cliente (path, query ou form) e sem checagem permitiria
`..`/`%2E%2E` saírem de `songs/` — e várias rotas apagam ou reescrevem a
pasta. Toda rota que monta `SONGS_DIR / slug` deve passar por aqui.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def safe_song_dir(songs_dir: Path, slug: str) -> Optional[Path]:
    """Devolve `songs_dir/slug` se for uma pasta filha direta; senão None."""
    if not slug or not isinstance(slug, str):
        return None
    if slug in (".", "..") or "/" in slug or "\\" in slug or "\x00" in slug:
        return None
    root = songs_dir.resolve()
    candidate = (root / slug).resolve()
    if candidate.parent != root:
        return None
    return candidate
