"""Helpers HTTP genéricos compartilhados entre routers."""
from __future__ import annotations

from fastapi import Response


def set_no_cache(response: Response) -> None:
    """Aplica headers anti-cache para endpoints cujo payload muda a cada hit."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
