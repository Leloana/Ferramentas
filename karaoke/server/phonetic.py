"""Chave de pronúncia de uma palavra, para a nota comparar o som além da escrita.

O Whisper às vezes escreve uma palavra parecida com a cantada e ela valia 0:
"Belisha" × "belly shot", "Amaterasu" × "amanteira", "pra que fazer" × "praquefazer".
Duas palavras com a mesma chave soam igual (ou quase) — `score_engine` aceita o par
quando as chaves batem bem, mesmo com a escrita longe.

- Inglês: Double Metaphone (o mesmo do `utils/lrc_realign.py`), sem vogais no meio.
- Português (e o resto): regras de som próprias — sem acento, ch/x, ç/ss/s, lh/li,
  nh/ni, rr/r, s entre vogais = z, qu/k, c antes de e/i = s, g antes de e/i = j,
  h mudo, letra dobrada vira uma, e/o átonos do fim viram i/u.
- Japonês: não passa por aqui (já compara pela leitura em romaji).
"""
from __future__ import annotations

import re
import unicodedata

from metaphone import doublemetaphone

_VOWELS = "aeiou"


def _plain(word: str) -> str:
    text = unicodedata.normalize("NFD", (word or "").lower().replace("ç", "ss"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z]", "", text)


_PT_RULES = [
    (r"ch", "x"), (r"sh", "x"), (r"lh", "li"), (r"nh", "ni"),
    (r"sc(?=[ei])", "s"), (r"x(?=c[ei])", "s"),
    (r"qu(?=[ei])", "k"), (r"gu(?=[ei])", "g"), (r"qu", "ku"),
    (r"c(?=[ei])", "s"), (r"c", "k"), (r"g(?=[ei])", "j"),
    (r"ss", "S"),  # "ss" segura o som de s; só o s sozinho entre vogais vira z
    (r"(?<=[aeiou])s(?=[aeiou])", "z"), (r"S", "s"),
    (r"h", ""), (r"y", "i"), (r"w", "u"), (r"rr", "r"),
    (r"(.)\1+", r"\1"),
    (r"e$", "i"), (r"o$", "u"), (r"es$", "is"), (r"os$", "us"),
    (r"m$", "n"), (r"z$", "s"),
]


def _pt_key(text: str) -> str:
    for pattern, repl in _PT_RULES:
        text = re.sub(pattern, repl, text)
    return text


def phonetic_key(word: str, language: str | None) -> str:
    """Chave de som da palavra (ou de várias palavras emendadas). "" se não há letras."""
    text = _plain(word)
    if not text:
        return ""
    if language and language.lower().startswith("en"):
        primary = doublemetaphone(text)[0]
        return primary.lower()
    return _pt_key(text)
