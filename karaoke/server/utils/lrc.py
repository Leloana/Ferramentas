"""Parsing leve do header de arquivos .lrc (tags [ti:] e [ar:])."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_lrc_meta(lrc_path: Path, fallback_title: str = "", fallback_artist: str = "") -> tuple[str, str]:
    """Lê apenas o header do .lrc até a primeira linha com timestamp.

    Retorna (title, artist), usando os fallbacks se as tags não existirem
    ou se houver erro de leitura.
    """
    title, artist = fallback_title, fallback_artist
    if not lrc_path.exists():
        return title, artist

    try:
        with open(lrc_path, "r", encoding="utf-8") as f:
            for line in f:
                line_clean = line.strip()
                if line_clean.startswith("[ti:"):
                    title = line_clean.split(":", 1)[1].rstrip("]").strip()
                elif line_clean.startswith("[ar:"):
                    artist = line_clean.split(":", 1)[1].rstrip("]").strip()
                # Linhas com timestamp começam com [HH ou [MM — fim do header.
                elif line_clean[:2] in ("[0", "[1", "[2"):
                    break
    except Exception as e:
        logger.debug(f"Falha ao ler header LRC {lrc_path}: {e}")

    return title, artist
