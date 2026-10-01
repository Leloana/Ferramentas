"""Palavras da letra por idioma: como dividir, juntar, comparar e romanizar.

Línguas com espaço (pt, en, es...) seguem `str.split()`, como sempre. Japonês
decide pela ESCRITA de cada linha, não só pelo idioma da música:

- linha com kanji/kana: tokenizada pelo MeCab (fugashi + unidic-lite) em
  *bunsetsu* — a palavra de conteúdo com as partículas/auxiliares que vêm depois
  ("遠ざかって" "いく日も" "見えない"), a unidade que o karaokê japonês acende —
  e ganha romaji para mostrar na tela;
- linha só em romaji (o usuário colou a letra romanizada): fica como veio,
  dividida por espaço, sem inventar kana;
- linha mista (J-pop com inglês): cada trecho segue a própria escrita.

Para comparar o cantado com a letra, japonês usa a PRONÚNCIA em romaji (は
partícula → "wa", を → "o"), que é como quem escreve romaji escreve; o STT pode
escrever a mesma palavra em kanji ou kana.
"""
from __future__ import annotations

import re
from functools import lru_cache

from unidecode import unidecode

# Tokens que não abrem um bunsetsu: grudam no anterior.
_JA_ATTACH_POS = {"助詞", "助動詞", "接尾辞", "補助記号"}
_JA_PREFIX_POS = "接頭辞"

_KANA_RE = re.compile(r"[\u3040-\u30ff]")  # hiragana + katakana
# kana + kanji (CJK unificado e extensão A) + 々
_JA_SCRIPT_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u3005]")


def is_japanese(language: str | None) -> bool:
    return bool(language) and language.lower().startswith("ja")


def has_japanese_script(text: str | None) -> bool:
    """O texto tem kanji ou kana (e não é só romaji)?"""
    return bool(text) and bool(_JA_SCRIPT_RE.search(text))


def _uses_bunsetsu(text: str, language: str | None) -> bool:
    return is_japanese(language) and has_japanese_script(text)


def infer_language(lyrics: str, chosen: str) -> str:
    """Idioma a usar, corrigindo o escolhido quando a letra denuncia japonês.

    Kana (hiragana/katakana) só existe em japonês; quem adiciona pelo celular
    raramente troca o idioma padrão do formulário. Letra só em romaji não é
    detectada: aí vale o idioma escolhido.
    """
    if not is_japanese(chosen) and lyrics and len(_KANA_RE.findall(lyrics)) >= 5:
        return "ja"
    return chosen


@lru_cache(maxsize=1)
def _tagger():
    import fugashi  # dicionário unidic-lite

    return fugashi.Tagger()


@lru_cache(maxsize=1)
def _kakasi():
    import pykakasi

    return pykakasi.kakasi()


def _ja_bunsetsu(text: str) -> list[tuple[str, int, int, str]]:
    """[(superfície, início, fim, pronúncia em kana)] com posições de caractere em `text`.

    Pronúncia é como se canta (は partícula → ワ, ー nas vogais longas).
    """
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
        pron = tok.feature.pron or kana
        if groups and (glue_next or pos1 in _JA_ATTACH_POS):
            g = groups[-1]
            g[0] += text[g[2]:end]  # inclui o que houver entre os tokens
            g[2] = end
            g[3] += pron
        elif pos1 == "補助記号":
            continue  # pontuação antes de qualquer palavra
        else:
            groups.append([surface, start, end, pron])
        glue_next = pos1 == _JA_PREFIX_POS
    return [tuple(g) for g in groups]


def split_words_with_spans(text: str, language: str | None) -> list[tuple[str, int, int]]:
    """Palavras da linha com o intervalo [início, fim) de cada uma em `text`."""
    if _uses_bunsetsu(text, language):
        return [(surface, start, end) for surface, start, end, _ in _ja_bunsetsu(text)]
    return [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def split_words(text: str, language: str | None) -> list[str]:
    """Palavras da linha, na unidade em que a letra acende e é pontuada."""
    return [surface for surface, _, _ in split_words_with_spans(text, language)]


def separator_between(left: str, right: str | None, language: str | None) -> str:
    """Espaço entre duas palavras vizinhas: nenhum entre duas em kanji/kana."""
    if is_japanese(language) and has_japanese_script(left) and (right is None or has_japanese_script(right)):
        return ""
    return " "


def join_words(words: list[str], language: str | None) -> str:
    out = ""
    for i, w in enumerate(words):
        out += w
        if i + 1 < len(words):
            out += separator_between(w, words[i + 1], language)
    return out


def _kana_to_romaji(kana: str, keep: str = "") -> str:
    romaji = "".join(item["hepburn"] for item in _kakasi().convert(kana))
    return re.sub(rf"[^a-z{keep}]", "", romaji.lower())


@lru_cache(maxsize=4096)
def ja_reading(word: str) -> str:
    """Chave de comparação (só a–z): pronúncia em romaji.

    Em romaji digitado pelo usuário, só normaliza (tōzakatte → tozakatte).
    """
    if not has_japanese_script(word):
        return re.sub(r"[^a-z]", "", unidecode(word).lower())
    pron = "".join(g[3] for g in _ja_bunsetsu(word)) or word
    # っ/ッ no fim vira "tsu" no pykakasi; é só a consoante dobrada do que vem depois.
    return _kana_to_romaji(re.sub(r"[っッ]+$", "", pron))


@lru_cache(maxsize=4096)
def ja_romaji(word: str) -> str:
    """Romaji para mostrar na tela: como se canta ("dokoe", "koewa", "toozakatte")."""
    if not has_japanese_script(word):
        return word
    return _kana_to_romaji("".join(g[3] for g in _ja_bunsetsu(word)), keep="'")


# kana, kanji e a pontuação japonesa
_JA_RANGES = ((0x3000, 0x303F), (0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF))
_JA_RUN = re.compile("[%s]+" % "".join(f"{chr(a)}-{chr(b)}" for a, b in _JA_RANGES))


def to_romaji(text: str) -> str:
    """Texto com trechos em japonês em romaji, palavra a palavra ("青い、濃い、橙色の日" →
    "aoi koi daidaiirono hi"). Sem japonês, volta igual."""
    if not text or not _JA_RUN.search(text):
        return text
    out = _JA_RUN.sub(lambda m: " " + " ".join(ja_romaji(w) for w in split_words(m.group(), "ja")) + " ", text)
    return re.sub(r"\s+", " ", out).strip()


def add_romaji(segments: list[dict]) -> list[dict]:
    """Acrescenta o romaji aos versos escritos em kanji/kana (in place): `lyrics_romaji`
    na linha e `romaji` em cada palavra. Letra que já é romaji não ganha nada (não se
    inventa kana), e os outros idiomas ficam como estão.

    Calculado ao carregar a música, então vale também para músicas já preparadas.
    """
    for seg in segments:
        if not _uses_bunsetsu(seg.get("lyrics", ""), seg.get("language")):
            continue
        words = seg.get("lyrics_timed") or []
        for w in words:
            w["romaji"] = ja_romaji(w["word"])
        romaji = [w["romaji"] for w in words] or [ja_romaji(x) for x in split_words(seg["lyrics"], "ja")]
        seg["lyrics_romaji"] = " ".join(r for r in romaji if r)
    return segments


def _heard_string(asr_words: list[dict], as_reading: bool) -> tuple[str, list[int]]:
    """Texto ouvido concatenado e, para cada caractere, o índice da palavra do STT dona dele.

    `as_reading`: converte para a pronúncia em romaji por bunsetsu (contexto
    certo para os kanji), para casar com uma letra em romaji.
    """
    heard, owner = "", []
    if not as_reading:
        for i, w in enumerate(asr_words):
            piece = w["word"].strip()
            heard += piece
            owner.extend([i] * len(piece))
        return heard, owner
    raw, raw_owner = _heard_string(asr_words, as_reading=False)
    for surface, start, end in split_words_with_spans(raw, "ja"):
        key = ja_reading(surface)
        heard += key
        # Cada letra da leitura aponta para o caractere proporcional do trecho escrito
        # (いく日も → "ikukamo": "mo" cai no も, não no início do grupo).
        span = end - start
        owner.extend(raw_owner[start + (k * span) // len(key)] for k in range(len(key)))
    return heard, owner


def _project(lyric_line: str, language: str | None, asr_words: list[dict]):
    """Casa, caractere a caractere, as palavras da letra com o que o STT ouviu.

    Letra em kanji/kana compara a escrita; letra em romaji compara a pronúncia.
    Devolve [(palavra, índices das palavras do STT casadas)] na ordem da letra.
    """
    from difflib import SequenceMatcher

    spans = split_words_with_spans(lyric_line, language)
    romaji_lyrics = is_japanese(language) and not has_japanese_script(lyric_line)
    if romaji_lyrics:
        text, word_spans = "", []
        for surface, _, _ in spans:
            key = ja_reading(surface)
            word_spans.append((surface, len(text), len(text) + len(key)))
            text += key
    else:
        text, word_spans = lyric_line, spans
    heard, owner = _heard_string(asr_words, as_reading=romaji_lyrics)
    text_to_heard: dict[int, int] = {}
    for block in SequenceMatcher(None, text, heard, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            text_to_heard[block.a + k] = block.b + k
    projected = []
    for surface, start, end in word_spans:
        hits = [text_to_heard[c] for c in range(start, end) if c in text_to_heard]
        projected.append((surface, hits, heard, owner))
    return projected


def time_words_by_characters(text: str, language: str | None, asr_words: list[dict]) -> list[dict]:
    """Tempos das palavras da letra a partir das palavras do STT, casando caractere a caractere.

    Serve para japonês na preparação da música: o STT (com a linha como dica)
    devolve pedaços em kana/kanji que não coincidem com as unidades da letra
    (nem com a letra em romaji). Palavra sem nenhum caractere casado ganha tempo
    interpolado entre as vizinhas.
    Retorna [{"word", "start", "end"}] com tempos relativos ao áudio do STT.
    """
    timed = []
    for surface, hits, _, owner in _project(text, language, asr_words):
        if hits:
            timed.append({"word": surface, "start": asr_words[owner[hits[0]]]["start"],
                          "end": asr_words[owner[hits[-1]]]["end"]})
        else:
            timed.append({"word": surface, "start": None, "end": None})

    # Interpolação das palavras sem casamento entre as vizinhas com tempo.
    known = [i for i, w in enumerate(timed) if w["start"] is not None]
    if not known:
        # Nada da linha foi ouvido (só ruído/alucinação): palavras espalhadas pelo trecho do STT
        if not timed or not asr_words:
            return timed
        lo, hi = float(asr_words[0]["start"]), max(float(asr_words[-1]["end"]), float(asr_words[0]["start"]))
        step = (hi - lo) / len(timed)
        for i, w in enumerate(timed):
            w["start"] = round(lo + step * i, 3)
            w["end"] = round(lo + step * (i + 1), 3)
        return timed
    for i, w in enumerate(timed):
        if w["start"] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        lo = timed[prev]["end"] if prev is not None else max(0.0, timed[nxt]["start"] - 0.3 * (nxt - i))
        hi = timed[nxt]["start"] if nxt is not None else timed[prev]["end"] + 0.3 * (i - prev)
        gaps = (nxt if nxt is not None else i + 1) - (prev if prev is not None else i - 1)
        hi = max(hi, lo)  # vizinhas casadas no mesmo trecho ouvido podem vir fora de ordem
        step = (hi - lo) / gaps
        pos = i - (prev if prev is not None else i - 1)
        w["start"] = round(lo + step * (pos - 1), 3)
        w["end"] = round(lo + step * pos, 3)
    return timed


def project_onto_romaji_lyrics(asr_words: list[dict], lyric_line: str) -> list[dict]:
    """Letra em romaji × STT em kana: o que foi ouvido sob cada palavra da letra.

    Para cada palavra da letra, devolve o trecho ouvido (pronúncia em romaji) que
    casou com ela, com o tempo e a confiança das palavras do STT de onde veio.
    Palavras sem casamento não aparecem (contam como não cantadas no score).
    """
    out = []
    for _, hits, heard, owner in _project(lyric_line, "ja", asr_words):
        if not hits:
            continue
        covered = asr_words[owner[hits[0]]:owner[hits[-1]] + 1]
        out.append({
            "word": heard[hits[0]:hits[-1] + 1],
            "start": covered[0]["start"],
            "end": covered[-1]["end"],
            "probability": sum(w.get("probability", 1.0) for w in covered) / len(covered),
        })
    return out


def regroup_timed_words(words: list[dict], language: str | None) -> list[dict]:
    """Palavras do STT (pedaços de 1–3 caracteres em japonês) → unidades da letra.

    Concatena o texto, tokeniza como a letra e dá a cada unidade o início do
    pedaço onde ela começa e o fim do pedaço onde termina. Fora do japonês, ou
    se o STT não escreveu nada em kanji/kana, devolve como veio.
    """
    if not is_japanese(language) or not words:
        return words
    text, owner = _heard_string(words, as_reading=False)
    if not has_japanese_script(text):
        return words
    out = []
    for surface, start, end in split_words_with_spans(text, language):
        covered = words[owner[start]:owner[end - 1] + 1]
        out.append({
            "word": surface,
            "start": covered[0]["start"],
            "end": covered[-1]["end"],
            "probability": sum(w.get("probability", 1.0) for w in covered) / len(covered),
        })
    return out
