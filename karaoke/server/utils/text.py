"""Utilitários de texto: slugify e parsing de tempo flexível."""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Converte texto para slug ASCII-safe (lowercase, sem acentos, com hífens)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text


def parse_time_to_seconds(time_str: str) -> float:
    """Aceita "4:30", "04:30.5", "1:02:03", "10" → segundos (float).

    Convenção: "-1" / "-1.0" / "" retornam -1.0 (sentinela "até o fim").
    Erros de parse retornam 0.0 e logam.
    """
    time_str = str(time_str).strip()
    if not time_str or time_str in ("-1.0", "-1"):
        return -1.0

    try:
        return float(time_str)
    except ValueError:
        pass

    parts = time_str.split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError as e:
        logger.error(f"Erro ao converter string de tempo '{time_str}': {e}")

    return 0.0
