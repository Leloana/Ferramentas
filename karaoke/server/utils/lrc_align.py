"""Alinha uma letra plana (texto puro, sem timestamps) com a saída do Whisper para gerar LRC.

Função pura: recebe a letra do usuário e os `segments` do faster-whisper
(com `word_timestamps=True`), devolve o texto LRC final e uma flag
indicando se caiu no fallback linear.

### Por que palavra-por-palavra em vez de linha-por-segmento?

A versão antiga mapeava `ref_line[i] → whisper_segment[j]` via match de
substring. Quando o VAD juntava vários versos num único segmento (caso
clássico: refrão sem pausa de 2s entre frases), N linhas de referência
casavam todas com o mesmo `j` e o algoritmo distribuía linearmente
dentro daquele segmento → 10 timestamps em 1 segundo (bug do Holiday).

A versão atual achata tudo em listas de palavras e usa
`difflib.SequenceMatcher` para achar a maior subsequência comum.
Palavras casadas viram âncoras temporais; o resto é interpolado linear
entre vizinhas casadas. O timestamp de cada linha = timestamp da
primeira palavra dela.
"""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Quando o matched-ratio total é muito baixo, abandona o alinhamento por
# palavra e distribui linearmente. Mesmo critério da versão antiga.
MIN_FALLBACK_MATCH_PCT = 0.15
MIN_FALLBACK_MATCHES = 3
LINEAR_FALLBACK_END_OFFSET = 5.0
LINEAR_FALLBACK_MIN_SPAN = 10.0
NO_LRC_LINE_INTERVAL_SEC = 4.0  # usado quando o Whisper não devolveu nada

# Injeção de marcador de pausa: gap entre fim de uma linha e início da
# próxima precisa ser maior que isso para virar uma linha vazia no LRC.
PAUSE_INJECT_MIN_GAP_SEC = 0.6

# Matching word-level com cursor forward-only:
WORD_SEARCH_WINDOW = 40  # quantas palavras à frente do cursor olhar
WORD_MIN_FUZZ_RATIO = 80  # rapidfuzz.ratio mínimo p/ aceitar match
# Limites realistas de taxa de canto (palavras/seg), usados na extrapolação
# de bordas. Ballads ~0.3 wps; rap denso ~2.5 wps.
RATE_MIN_SEC_PER_WORD = 0.15
RATE_MAX_SEC_PER_WORD = 1.5
DEFAULT_SEC_PER_WORD = 0.4


def _format_timestamp(t: float) -> str:
    m = int(t // 60)
    s = int(t % 60)
    ms = int((t % 1) * 100)
    return f"[{m:02d}:{s:02d}.{ms:02d}]"


def _parse_ref_lines(plain_lyrics: str) -> list[str]:
    """Remove linhas em branco e diretivas LRC ([tag:...]) do texto do usuário."""
    out = []
    for line in plain_lyrics.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") and "]" in s:
            continue
        out.append(s)
    return out


def _normalize_word(w: str) -> str:
    """Lowercase + remove pontuação. Vazia se sobrou nada."""
    return re.sub(r"[^\w]", "", w.lower())


def _flatten_ref(ref_lines: list[str]) -> tuple[list[str], list[int]]:
    """Achata todas as palavras das ref_lines numa lista única.

    Retorna `(tokens, line_idx_of_token)`, onde `line_idx_of_token[k]`
    diz a qual ref_line a palavra `tokens[k]` pertence.
    """
    tokens: list[str] = []
    line_idx: list[int] = []
    for i, line in enumerate(ref_lines):
        for raw in line.split():
            norm = _normalize_word(raw)
            if not norm:
                continue
            tokens.append(norm)
            line_idx.append(i)
    return tokens, line_idx


def _flatten_whisper(whisper_segments: list) -> list[dict]:
    """Achata `segments[].words[]` do faster-whisper numa lista única."""
    out = []
    for seg in whisper_segments:
        words = getattr(seg, "words", None) or []
        for w in words:
            norm = _normalize_word(w.word)
            if not norm:
                continue
            out.append({"word": norm, "start": float(w.start), "end": float(w.end)})
    return out


def _clamp_rate(sec_per_word: float) -> float:
    """Clipa a taxa estimada (s/palavra) em limites musicalmente realistas."""
    return max(RATE_MIN_SEC_PER_WORD, min(sec_per_word, RATE_MAX_SEC_PER_WORD))


def _interp_unmatched(times: list[float | None]) -> list[float]:
    """Preenche `None` por interpolação entre âncoras conhecidas.

    Estratégia:
    - Entre duas âncoras: interpolação linear (taxa local).
    - Antes da primeira âncora: extrapola usando a taxa estimada das 2
      primeiras âncoras (ou um default conservador se só há 1).
    - Depois da última âncora: extrapola usando a taxa das 2 últimas.
    - Monotonicidade forçada com delta mínimo de 0.01s.

    Isso é melhor que a versão anterior (que empacotava as palavras de
    borda em 100ms/300ms fixos) porque respeita a taxa real de canto
    estimada pelos vizinhos.
    """
    n = len(times)
    if n == 0:
        return []

    anchors = [i for i, t in enumerate(times) if t is not None]
    if not anchors:
        return [0.0] * n

    result: list[float] = [0.0] * n

    # Estima taxa da borda inicial (s/palavra) usando as 2 primeiras âncoras
    if len(anchors) >= 2:
        a0, a1 = anchors[0], anchors[1]
        rate_start = _clamp_rate((times[a1] - times[a0]) / max(1, a1 - a0))
    else:
        rate_start = DEFAULT_SEC_PER_WORD

    # Antes da primeira âncora
    first = anchors[0]
    t0 = times[first]
    for i in range(first):
        result[i] = max(0.0, t0 - rate_start * (first - i))

    # Entre cada par de âncoras consecutivas
    for a, b in zip(anchors, anchors[1:]):
        ta, tb = times[a], times[b]
        result[a] = ta
        gap = b - a
        if gap > 1:
            step = (tb - ta) / gap
            for k in range(1, gap):
                result[a + k] = ta + step * k
        result[b] = tb

    # Estima taxa da borda final
    if len(anchors) >= 2:
        am1, am2 = anchors[-1], anchors[-2]
        rate_end = _clamp_rate((times[am1] - times[am2]) / max(1, am1 - am2))
    else:
        rate_end = DEFAULT_SEC_PER_WORD

    last = anchors[-1]
    for i in range(last + 1, n):
        result[i] = times[last] + rate_end * (i - last)

    # Força monotonicidade
    for i in range(1, n):
        if result[i] < result[i - 1] + 0.01:
            result[i] = result[i - 1] + 0.01
    return result


def _align_word_level(ref_tokens: list[str], whisper_words: list[dict]) -> tuple[list[float | None], list[float | None], int]:
    """Casa `ref_tokens` com `whisper_words` via cursor forward-only + fuzzy.

    Para cada palavra da letra, busca o melhor match nas próximas
    `WORD_SEARCH_WINDOW` palavras do Whisper a partir do cursor (`rapidfuzz.ratio`
    >= `WORD_MIN_FUZZ_RATIO`). Se achar, ancora e avança o cursor para depois
    do match — isso preserva ordem e lida corretamente com refrões repetidos
    (cada ocorrência pega seu próprio anchor).

    Por que não SequenceMatcher: ele busca a maior subseq comum globalmente.
    Com 3 refrões idênticos na letra, ele tende a casar todas as 3
    ocorrências da letra com a MESMA transcrição do Whisper (a primeira que
    cabe na maior subseq), deixando as outras 2 sem âncora.

    Retorna `(starts, ends, n_matched)`.
    """
    n = len(ref_tokens)
    starts: list[float | None] = [None] * n
    ends: list[float | None] = [None] * n

    if not whisper_words:
        return starts, ends, 0

    wh_tokens = [w["word"] for w in whisper_words]
    m = len(wh_tokens)
    cursor = 0
    matched = 0

    for i, ref_word in enumerate(ref_tokens):
        if not ref_word:
            continue
        best_j = -1
        best_ratio = 0
        window_end = min(m, cursor + WORD_SEARCH_WINDOW)
        for j in range(cursor, window_end):
            r = fuzz.ratio(ref_word, wh_tokens[j])
            if r > best_ratio:
                best_ratio = r
                best_j = j
                if r == 100:
                    break

        if best_j != -1 and best_ratio >= WORD_MIN_FUZZ_RATIO:
            starts[i] = whisper_words[best_j]["start"]
            ends[i] = whisper_words[best_j]["end"]
            matched += 1
            cursor = best_j + 1

    return starts, ends, matched


def align_plain_lyrics(
    plain_lyrics: str,
    whisper_segments: list,
    title: str,
    artist: str,
    total_vocal_duration_sec: float,
) -> tuple[str, bool]:
    """Retorna (texto_lrc, fallback_used).

    `whisper_segments` é a sequência de `Segment` do `faster_whisper`
    (cada item com `.words[]` — exige `word_timestamps=True` na chamada
    de transcrição).
    """
    ref_lines = _parse_ref_lines(plain_lyrics)
    lrc_lines = [f"[ti:{title}]", f"[ar:{artist}]", ""]

    if not ref_lines:
        return "\n".join(lrc_lines), False

    ref_tokens, line_idx = _flatten_ref(ref_lines)
    whisper_words = _flatten_whisper(whisper_segments)

    logger.info(
        f"🔎 [LRC ALIGN] '{title}': {len(ref_lines)} linhas / {len(ref_tokens)} palavras de referência; "
        f"Whisper devolveu {len(whisper_words)} palavras."
    )

    n_lines = len(ref_lines)

    # --- Fallback total: Whisper não devolveu palavras ---
    if not whisper_words:
        last_t = 0.0
        for i, ref in enumerate(ref_lines):
            t = last_t + i * NO_LRC_LINE_INTERVAL_SEC
            lrc_lines.append(f"{_format_timestamp(t)}{ref}")
        return "\n".join(lrc_lines), False

    # --- Matching word-level via SequenceMatcher ---
    word_starts, word_ends, matched = _align_word_level(ref_tokens, whisper_words)
    match_ratio = matched / max(1, len(ref_tokens))
    logger.info(f"🔎 [LRC ALIGN] Matched {matched}/{len(ref_tokens)} palavras ({match_ratio:.0%}).")

    # --- Fallback linear se quase nada bateu ---
    min_needed = max(MIN_FALLBACK_MATCHES, int(n_lines * MIN_FALLBACK_MATCH_PCT))
    if matched < min_needed:
        logger.info(
            f"⚠️  [LRC ALIGN] Apenas {matched} palavras casadas (mínimo: {min_needed}). "
            f"Distribuindo linearmente."
        )
        start_t = 0.0
        end_t = max(start_t + LINEAR_FALLBACK_MIN_SPAN, total_vocal_duration_sec - LINEAR_FALLBACK_END_OFFSET)
        step = (end_t - start_t) / max(1, n_lines - 1)
        line_starts = [start_t + i * step for i in range(n_lines)]
        line_ends = [line_starts[i] + step * 0.8 for i in range(n_lines)]
        return _render_lrc(lrc_lines, ref_lines, line_starts, line_ends), True

    # --- Caso normal: interpola palavras não-casadas ---
    full_word_starts = _interp_unmatched(word_starts)

    # Tempo de cada linha = início da primeira palavra dela.
    line_starts: list[float] = [0.0] * n_lines
    seen = set()
    for token_idx, li in enumerate(line_idx):
        if li in seen:
            continue
        seen.add(li)
        line_starts[li] = full_word_starts[token_idx]

    # Tempo de fim de cada linha = fim da última palavra casada da linha;
    # se nenhuma palavra da linha foi casada, infere a partir da próxima
    # linha (gap pequeno) ou do total_duration na última.
    line_ends: list[float] = [0.0] * n_lines
    for li in range(n_lines):
        last_end: float | None = None
        for token_idx, ln in enumerate(line_idx):
            if ln == li and word_ends[token_idx] is not None:
                last_end = word_ends[token_idx]
        if last_end is None:
            next_start = line_starts[li + 1] if li + 1 < n_lines else (line_starts[li] + 3.0)
            last_end = min(next_start - 0.1, line_starts[li] + 4.0)
        line_ends[li] = last_end

    # Força monotonicidade entre starts (linhas no LRC precisam estar em ordem)
    for i in range(1, n_lines):
        if line_starts[i] < line_starts[i - 1] + 0.05:
            line_starts[i] = line_starts[i - 1] + 0.05

    return _render_lrc(lrc_lines, ref_lines, line_starts, line_ends), False


def _render_lrc(header: list[str], ref_lines: list[str], starts: list[float], ends: list[float]) -> str:
    """Monta o LRC final injetando marcadores de pausa em gaps grandes."""
    out = list(header)
    n = len(ref_lines)
    for i, ref in enumerate(ref_lines):
        out.append(f"{_format_timestamp(starts[i])}{ref}")
        end_t = ends[i]
        next_start = starts[i + 1] if i + 1 < n else (end_t + 2.0)
        # Recua o fim para não encavalar
        if end_t >= next_start:
            end_t = next_start - 0.05
        if (next_start - end_t) > PAUSE_INJECT_MIN_GAP_SEC:
            out.append(f"{_format_timestamp(end_t)} ")
    clean = [line.strip() for line in out if line.strip()]
    return "\n".join(clean)


def draft_lrc_from_whisper(
    whisper_segments: list,
    title: str,
    artist: str,
) -> str:
    """Gera rascunho LRC direto da saída do Whisper (sem letra de referência)."""
    lrc_lines = [f"[ti:{title}]", f"[ar:{artist}]", ""]
    for seg in whisper_segments:
        lrc_lines.append(f"{_format_timestamp(seg.start)}{seg.text.strip()}")
    return "\n".join(lrc_lines)
