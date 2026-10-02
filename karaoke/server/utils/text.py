"""Utilitários de texto: slugify, parsing de tempo flexível e normalização de letras."""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def normalize_lyrics_text(text: str | None) -> str:
    """Normaliza letras planas para gravação consistente em `lyrics.txt`/`meta.json`.

    Operações aplicadas (idempotentes):
    - `\\r\\n` → `\\n` (Windows → Unix)
    - `\\r` solto → `\\n` (Mac antigo)
    - `strip()` em cada linha
    - Remove linhas vazias consecutivas (mantém no máximo uma linha em branco
      entre versos — útil para preservar separação visual sem inflar arquivos)
    - `strip()` final do bloco inteiro

    O bug que motivou: `meta.json` salvava `"\\r\\n\\r\\n"` (vindo do Windows),
    e `reinstall_song.py` gravava esse conteúdo cru no `lyrics.txt`, gerando
    linhas com `^M` (CR) no Linux/Mac e versos duplamente espaçados.
    """
    if not text:
        return ""
    # Normaliza line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = join_split_words(text)
    # Strip por linha + colapsa linhas vazias consecutivas
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        if not ln:
            if prev_blank:
                continue
            prev_blank = True
        else:
            prev_blank = False
        out.append(ln)
    return "\n".join(out).strip()


_LRC_TAGS_RE = re.compile(r"^((?:\s*\[\d+:\d+(?:[.:]\d+)?\])*)(.*)$")
_SPLIT_END_RE = re.compile(r"[^\W\d_]-$")


def join_split_words(text: str) -> str:
    """Junta a palavra partida entre duas linhas ("My un-" / "cle Bill" → "My uncle Bill").

    Vale para letra simples e LRC: a linha que termina em letra + hífen e a seguinte
    começa com minúscula viram uma só, com o tempo da primeira. Um travessão solto
    ("vai -") ou a marca vazia de fim de verso do LRC não juntam nada.
    """
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if out:
            tags, prev = _LRC_TAGS_RE.match(out[-1]).groups()
            rest = _LRC_TAGS_RE.match(line).group(2).strip()
            prev = prev.rstrip()
            if _SPLIT_END_RE.search(prev) and rest[:1].islower():
                out[-1] = f"{tags}{prev[:-1]}{rest}"
                continue
        out.append(line)
    return "\n".join(out)


def slugify(text: str) -> str:
    """Converte texto para slug ASCII-safe (lowercase, sem acentos, com hífens)."""
    # japonês vira romaji ("青い、濃い" → "aoi koi"): o ASCII descartaria tudo
    from lyrics_text import to_romaji  # sob demanda: servidor e ferramentas têm server/ no path

    text = to_romaji(text)
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
