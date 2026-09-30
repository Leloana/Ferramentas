"""Palavras da letra por idioma: como dividir, juntar e comparar.

Línguas com espaço (pt, en, es...) seguem `str.split()`, como sempre. Japonês não
tem espaço: a linha é tokenizada pelo MeCab (fugashi + unidic-lite) e os tokens
viram *bunsetsu* — a palavra de conteúdo com as partículas/auxiliares que vêm
depois ("遠ざかって" "いく日も" "見えない"), a unidade que o karaokê japonês acende.

Para comparar o cantado com a letra, japonês usa a leitura em romaji tirada do
contexto (日 → ひ → "hi"): o STT pode escrever a mesma palavra em kanji ou kana.
"""
from __future__ import annotations

import re
from functools import lru_cache

# Tokens que não abrem um bunsetsu: grudam no anterior.
_JA_ATTACH_POS = {"助詞", "助動詞", "接尾辞", "補助記号"}
_JA_PREFIX_POS = "接頭辞"


def is_japanese(language: str | None) -> bool:
    return bool(language) and language.lower().startswith("ja")


_KANA_RE = re.compile(r"[぀-ヿ]")  # hiragana + katakana


def infer_language(lyrics: str, chosen: str) -> str:
    """Idioma a usar, corrigindo o escolhido quando a letra denuncia japonês.

    Kana (hiragana/katakana) só existe em japonês; quem adiciona pelo celular
    raramente troca o idioma padrão do formulário.
    """
    if not is_japanese(chosen) and lyrics and len(_KANA_RE.findall(lyrics)) >= 5:
        return "ja"
    return chosen


def word_separator(language: str | None) -> str:
    return "" if is_japanese(language) else " "


@lru_cache(maxsize=1)
def _tagger():
    import fugashi  # dicionário unidic-lite

    return fugashi.Tagger()


@lru_cache(maxsize=1)
def _kakasi():
    import pykakasi

    return pykakasi.kakasi()


def _ja_bunsetsu(text: str) -> list[tuple[str, int, int, str]]:
    """[(superfície, início, fim, leitura em kana)] com posições de caractere em `text`."""
    groups: list[list] = []
    pos = 0
    glue_next = False  # último token foi prefixo: o próximo continua o grupo
    for tok in _tagger()(text):
        surface = tok.surface
        start = text.find(surface, pos)
        if start < 0:
            continue
        end = start + len(surface)
        pos = end
        pos1 = tok.feature.pos1
        kana = tok.feature.kana or ("" if pos1 == "補助記号" else surface)
        if groups and (glue_next or pos1 in _JA_ATTACH_POS):
            g = groups[-1]
            g[0] += text[g[2]:end]  # inclui o que houver entre os tokens
            g[2] = end
            g[3] += kana
        elif pos1 == "補助記号":
            continue  # pontuação antes de qualquer palavra
        else:
            groups.append([surface, start, end, kana])
        glue_next = pos1 == _JA_PREFIX_POS
    return [(g[0], g[1], g[2], g[3]) for g in groups]


def split_words(text: str, language: str | None) -> list[str]:
    """Palavras da linha, na unidade em que a letra acende e é pontuada."""
    if is_japanese(language):
        return [surface for surface, *_ in _ja_bunsetsu(text)]
    return text.split()


def split_words_with_spans(text: str, language: str | None) -> list[tuple[str, int, int]]:
    """Como `split_words`, com o intervalo [início, fim) de cada palavra em `text`."""
    if is_japanese(language):
        return [(surface, start, end) for surface, start, end, _ in _ja_bunsetsu(text)]
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def join_words(words: list[str], language: str | None) -> str:
    return word_separator(language).join(words)


def _kana_to_romaji(kana: str) -> str:
    romaji = "".join(item["hepburn"] for item in _kakasi().convert(kana))
    return re.sub(r"[^a-z]", "", romaji.lower())


@lru_cache(maxsize=4096)
def ja_reading(word: str) -> str:
    """Leitura em romaji (só a–z) de um trecho em japonês, pela leitura em contexto."""
    groups = _ja_bunsetsu(word)
    kana = "".join(g[3] for g in groups) if groups else word
    # っ/ッ no fim vira "tsu" no pykakasi; é só a consoante dobrada do que vem depois.
    kana = re.sub(r"[っッ]+$", "", kana)
    return _kana_to_romaji(kana)


def time_words_by_characters(text: str, language: str | None, asr_words: list[dict]) -> list[dict]:
    """Tempos das palavras da letra a partir das palavras do STT, casando caractere a caractere.

    Serve para japonês na preparação da música: o STT (com a linha como dica)
    devolve pedaços que não coincidem com as unidades da letra. Palavra sem
    nenhum caractere casado ganha tempo interpolado entre as vizinhas.
    Retorna [{"word", "start", "end"}] com tempos relativos ao áudio do STT.
    """
    from difflib import SequenceMatcher

    heard = ""
    owner: list[int] = []
    for i, w in enumerate(asr_words):
        piece = w["word"].strip()
        heard += piece
        owner.extend([i] * len(piece))
    text_to_heard: dict[int, int] = {}
    for block in SequenceMatcher(None, text, heard, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            text_to_heard[block.a + k] = block.b + k

    timed = []
    for surface, start, end in split_words_with_spans(text, language):
        hits = [text_to_heard[c] for c in range(start, end) if c in text_to_heard]
        if hits:
            timed.append({"word": surface, "start": asr_words[owner[hits[0]]]["start"],
                          "end": asr_words[owner[hits[-1]]]["end"]})
        else:
            timed.append({"word": surface, "start": None, "end": None})

    # Interpolação das palavras sem casamento entre as vizinhas com tempo.
    known = [i for i, w in enumerate(timed) if w["start"] is not None]
    if not known:
        return timed
    for i, w in enumerate(timed):
        if w["start"] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        lo = timed[prev]["end"] if prev is not None else max(0.0, timed[nxt]["start"] - 0.3 * (nxt - i))
        hi = timed[nxt]["start"] if nxt is not None else timed[prev]["end"] + 0.3 * (i - prev)
        gaps = (nxt if nxt is not None else i + 1) - (prev if prev is not None else i - 1)
        step = (hi - lo) / gaps
        pos = i - (prev if prev is not None else i - 1)
        w["start"] = round(lo + step * (pos - 1), 3)
        w["end"] = round(lo + step * pos, 3)
    return timed


def regroup_timed_words(words: list[dict], language: str | None) -> list[dict]:
    """Palavras do STT (pedaços de 1–3 caracteres em japonês) → unidades da letra.

    Concatena o texto, tokeniza como a letra e dá a cada unidade o início do
    pedaço onde ela começa e o fim do pedaço onde termina. Fora do japonês,
    devolve como veio.
    """
    if not is_japanese(language) or not words:
        return words
    text = ""
    owner: list[int] = []  # índice do pedaço dono de cada caractere
    for i, w in enumerate(words):
        piece = w["word"].strip()
        text += piece
        owner.extend([i] * len(piece))
    out = []
    for surface, start, end in split_words_with_spans(text, language):
        first, last = words[owner[start]], words[owner[end - 1]]
        covered = words[owner[start]:owner[end - 1] + 1]
        out.append({
            "word": surface,
            "start": first["start"],
            "end": last["end"],
            "probability": sum(w.get("probability", 1.0) for w in covered) / len(covered),
        })
    return out
