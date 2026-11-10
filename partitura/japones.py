"""Letra em japonês embaixo das notas: uma mora por nota, em romaji ou kana. Sem LLM.

No canto japonês a unidade rítmica é a mora (cada kana), não a sílaba: 空 (sora) = so-ra,
東京 (tōkyō) = to-o-kyo-o. A pronúncia como se canta (は partícula -> wa, vogal longa ー)
vem do analisador do karaokê (fugashi + dicionário unidic-lite, em
karaoke/server/lyrics_text.py); sem ele, do pykakasi. Regras de corte:
- kana pequeno (ゃゅょぁぃぅぇぉ) junta com o anterior: きょ = kyo, uma mora;
- ー (vogal longa) e っ (consoante dobrada) também ficam com a mora anterior: a nota
  da mora segura o tempo (ー) ou corta seco (っ), sem sílaba própria;
- ん é mora própria (n).
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

KARAOKE_SERVER = Path(__file__).resolve().parent.parent / "karaoke" / "server"
PEQUENOS = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")
JUNTA = set("ーっッ")
_JA = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


def tem_japones(texto: str) -> bool:
    return bool(_JA.search(texto or ""))


@lru_cache(maxsize=1)
def _kakasi():
    import pykakasi
    return pykakasi.kakasi()


@lru_cache(maxsize=4096)
def pronuncia(palavra: str) -> str:
    """Pronúncia em katakana como se canta."""
    try:
        if str(KARAOKE_SERVER) not in sys.path:
            sys.path.append(str(KARAOKE_SERVER))
        from lyrics_text import _ja_bunsetsu
        pron = "".join(g[3] for g in _ja_bunsetsu(palavra))
        if pron:
            return pron
    except Exception:
        pass
    return "".join(item["kana"] for item in _kakasi().convert(palavra))


def moras(kana: str) -> list[str]:
    saida = []
    for ch in kana:
        if not ch.strip():
            continue
        if (ch in PEQUENOS or ch in JUNTA) and saida:
            saida[-1] += ch
        elif ch in JUNTA:
            continue
        else:
            saida.append(ch)
    return saida


def _romaji(kana: str) -> str:
    return re.sub(r"[^a-z']", "", "".join(i["hepburn"] for i in _kakasi().convert(kana)).lower())


def _hiragana(kana: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in kana)


def silabas_japonesas(palavra: str, escrita: str = "romaji") -> list[str]:
    """['so', 'ra', 'wa'] (romaji) ou ['そ', 'ら', 'わ'] (kana). Pontuação vai na última."""
    m = re.match(r"^(.*?)([、。！？!?,.…]*)$", palavra)
    corpo, pont = (m.group(1), m.group(2)) if m else (palavra, "")
    if not tem_japones(corpo):
        return [palavra]
    ms = moras(pronuncia(corpo))
    if not ms:
        return [palavra]
    if escrita == "kana":
        partes = [_hiragana(x) for x in ms]
    else:
        partes = []
        for i, x in enumerate(ms):
            base = x.rstrip("ーっッ")
            r = _romaji(base) if base else ""
            if "ー" in x[len(base):] and r:
                r += r[-1]                       # vogal longa: toー -> too
            if x[len(base):].endswith(("っ", "ッ")) and i + 1 < len(ms):
                prox = _romaji(ms[i + 1].rstrip("ーっッ"))
                if prox and prox[0] not in "aeiou":
                    r += "t" if prox.startswith("ch") else prox[0]   # っ: dobra a consoante seguinte
            partes.append(r or x)
    partes[-1] += pont
    return partes
