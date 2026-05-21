"""Alinha uma letra plana (texto puro, sem timestamps) com a saída do Whisper para gerar LRC.

Função pura: recebe a letra do usuário e os `segments` do faster-whisper
(com `word_timestamps=True`), devolve o texto LRC final e uma flag
indicando se caiu no fallback linear.

### Estratégia atual

1. Achata palavras da letra e do Whisper em duas listas paralelas.
2. Casa palavra-a-palavra com **cursor forward-only + fuzzy match**
   (rapidfuzz.ratio >= 80, janela de 40 à frente).
3. Para cada **linha da letra**, conta quantas palavras dela foram
   casadas:
   - **>= 1 match** → linha "confiável", recebe timestamp da primeira
     palavra casada
   - **0 matches** → linha "órfã", recebe `[??:??.??]` (placeholder)
     visível no LRC, para o usuário ajustar manualmente

Regra de ouro: **não inventar timestamps**. Se o Whisper não ouviu
nada da linha, melhor sinalizar do que extrapolar errado e o usuário
não perceber. Isso resolve casos como "(Say: Hey! Cha!)" (grito não
lexical, que o Whisper geralmente pula ou transcreve genericamente),
"(The representative from California has the floor)" (fala distorcida
no início de Holiday), etc.

### Por que cursor forward-only

`difflib.SequenceMatcher` (versão anterior) busca a maior subseq
comum globalmente — em letras com refrão repetido, casa todas as 3
ocorrências da letra com a MESMA região do Whisper. Cursor avançante
garante que cada ocorrência do refrão pegue suas próprias âncoras.
"""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Quando o número de matches é muito baixo, abandona o alinhamento por
# palavra e distribui linearmente (mesmo critério da versão antiga).
MIN_FALLBACK_MATCH_PCT = 0.15
MIN_FALLBACK_MATCHES = 3
LINEAR_FALLBACK_END_OFFSET = 5.0
LINEAR_FALLBACK_MIN_SPAN = 10.0
NO_LRC_LINE_INTERVAL_SEC = 4.0  # usado quando o Whisper não devolveu nada

# Gap mínimo (em segundos) entre fim de uma linha confiável e início da
# próxima para emitir um marcador de pausa LRC.
PAUSE_INJECT_MIN_GAP_SEC = 0.6

# Matching word-level (cursor forward-only):
WORD_SEARCH_WINDOW = 40    # palavras à frente do cursor no Whisper
WORD_MIN_FUZZ_RATIO = 80   # rapidfuzz.ratio mínimo p/ aceitar match

# Placeholder de timestamp para linhas órfãs (sem nenhuma palavra casada).
# Formato é deliberadamente inválido para players LRC (que pulam a linha)
# mas visível no editor para o usuário corrigir.
ORPHAN_TIMESTAMP = "[??:??.??]"


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
    """Achata palavras das ref_lines numa lista única.

    Retorna `(tokens, line_idx_of_token)`. Tokens vazios após
    normalização (ex.: "(", "!") são descartados — então uma linha
    como "(Say: Hey! Cha!)" vira tokens `["say", "hey", "cha"]`.
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


def _align_word_level(ref_tokens: list[str], whisper_words: list[dict]) -> tuple[list[float | None], list[float | None], int]:
    """Casa `ref_tokens` com `whisper_words` via cursor forward-only + fuzzy.

    Para cada palavra da letra, busca o melhor match nas próximas
    `WORD_SEARCH_WINDOW` palavras do Whisper a partir do cursor
    (`rapidfuzz.ratio >= WORD_MIN_FUZZ_RATIO`). Se achar, ancora e
    avança o cursor para depois do match.

    Retorna `(starts, ends, n_matched)` — arrays do tamanho de
    `ref_tokens` com `None` onde não casou.
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

    Linhas órfãs (sem nenhuma palavra casada) saem com `[??:??.??]` em
    vez de timestamp inventado — o usuário decide o tempo correto.
    """
    ref_lines = _parse_ref_lines(plain_lyrics)
    lrc_lines = [f"[ti:{title}]", f"[ar:{artist}]", ""]

    if not ref_lines:
        return "\n".join(lrc_lines), False

    ref_tokens, line_idx = _flatten_ref(ref_lines)
    whisper_words = _flatten_whisper(whisper_segments)
    n_lines = len(ref_lines)

    logger.info(
        f"🔎 [LRC ALIGN] '{title}': {n_lines} linhas / {len(ref_tokens)} palavras de referência; "
        f"Whisper devolveu {len(whisper_words)} palavras."
    )

    # --- Fallback total: Whisper não devolveu palavras ---
    if not whisper_words:
        for i, ref in enumerate(ref_lines):
            t = i * NO_LRC_LINE_INTERVAL_SEC
            lrc_lines.append(f"{_format_timestamp(t)}{ref}")
        return "\n".join(lrc_lines), False

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
        for i, ref in enumerate(ref_lines):
            t = start_t + i * step
            lrc_lines.append(f"{_format_timestamp(t)}{ref}")
        return "\n".join(lrc_lines), True

    # --- Análise por linha ---
    line_start: list[float | None] = [None] * n_lines
    line_end: list[float | None] = [None] * n_lines
    line_match_count = [0] * n_lines
    for token_idx, li in enumerate(line_idx):
        if word_starts[token_idx] is None:
            continue
        line_match_count[li] += 1
        ws = word_starts[token_idx]
        we = word_ends[token_idx]
        if line_start[li] is None or ws < line_start[li]:
            line_start[li] = ws
        if line_end[li] is None or (we is not None and we > line_end[li]):
            line_end[li] = we

    # Força monotonicidade APENAS entre linhas confiáveis (Whisper às vezes
    # produz word timestamps fora de ordem em vocais com forte reverb).
    confident = [i for i in range(n_lines) if line_match_count[i] > 0]
    for k in range(1, len(confident)):
        prev_i = confident[k - 1]
        curr_i = confident[k]
        if line_start[curr_i] < line_start[prev_i] + 0.05:
            line_start[curr_i] = line_start[prev_i] + 0.05

    # --- Render ---
    orphan_count = 0
    for li, ref in enumerate(ref_lines):
        if line_match_count[li] > 0:
            t = line_start[li]
            lrc_lines.append(f"{_format_timestamp(t)}{ref}")

            # Pausa: gap até a PRÓXIMA linha confiável (pula órfãs)
            next_conf = li + 1
            while next_conf < n_lines and line_match_count[next_conf] == 0:
                next_conf += 1
            if next_conf < n_lines:
                end_t = line_end[li] if line_end[li] is not None else t
                next_t = line_start[next_conf]
                if end_t >= next_t:
                    end_t = next_t - 0.05
                if (next_t - end_t) > PAUSE_INJECT_MIN_GAP_SEC:
                    lrc_lines.append(f"{_format_timestamp(end_t)} ")
        else:
            lrc_lines.append(f"{ORPHAN_TIMESTAMP}{ref}")
            orphan_count += 1

    if orphan_count > 0:
        logger.info(
            f"⚠️  [LRC ALIGN] {orphan_count} linha(s) sem match — marcadas com {ORPHAN_TIMESTAMP} "
            f"para edição manual. O Whisper provavelmente não capturou esses trechos "
            f"(vocalize, grito não-lexical, fala distorcida, etc.)."
        )

    clean = [line.strip() for line in lrc_lines if line.strip()]
    return "\n".join(clean), False


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
