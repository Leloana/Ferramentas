"""Onde cada linha da letra foi cantada neste áudio, pela transcrição do Whisper.

Para quando a versão do áudio não é a da letra: refrão a mais, verso cortado,
ponte que não existe. O LRC do LRCLIB (se houver) não ajuda aqui, porque os
tempos são de outra estrutura.

1. Programação dinâmica palavra a palavra entre a letra e a transcrição, em
   ordem nos dois lados. Pular palavra da transcrição é barato (ruído, refrão
   extra, alucinação). Pular palavra da letra custa mais (trecho não cantado).
2. Linha com palavras suficientes casadas vira âncora (início e fim pelo Whisper).
3. Linhas sem âncora entre duas âncoras: se há voz no intervalo, são distribuídas
   pelo tempo COM VOZ dele. Se quase não há voz, a versão não canta essas linhas
   e elas saem.
4. Trechos da transcrição que sobraram sem linha (refrão repetido a mais) são
   procurados na letra inteira (alinhamento local). Achou: as linhas entram de
   novo, repetidas, naquele tempo.

O Whisper erra muito em canto ("trim and devour" no lugar de "dream and
differ"): os limiares aceitam casamento parcial e uma linha só precisa de
parte das palavras para ancorar. O tempo fino de cada palavra continua sendo
do MMS_FA, dentro da janela que este plano dá para a linha.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np
from rapidfuzz import fuzz
from rapidfuzz.process import cdist
from unidecode import unidecode

from lyrics_text import is_japanese, ja_reading, regroup_timed_words, split_words

logger = logging.getLogger(__name__)

# casamento palavra × palavra (rapidfuzz.ratio)
SIM_FULL, SIM_PARTIAL = 85, 70
SCORE_FULL, SCORE_PARTIAL, SCORE_MISMATCH = 2.0, 1.0, -1.0
GAP_LYRIC = -0.6        # palavra da letra sem par
GAP_TRANSCRIPT = -0.3   # palavra da transcrição sem par
# linha ancorada: fração mínima de palavras casadas, ou um mínimo absoluto, e
# letras casadas suficientes ("four"~"our" sozinho não prova "(Three, four)").
# Casamento parcial vale metade.
ANCHOR_MIN_FRACTION = 0.34
ANCHOR_MIN_WORDS = 3
ANCHOR_MIN_CHARS = 8
# pista fraca (linha sem âncora que pode ficar num intervalo curto): palavra
# exata da letra com pelo menos isso de letras ("a" não é pista)
HINT_MIN_CHARS = 2
# palavra da letra sem par na ponta da linha: quanto ela estende a âncora
EDGE_WORD_SEC = 0.3
# linhas sem âncora: duração estimada e voz mínima para ficarem
SEC_PER_SYLLABLE = 0.28
LINE_MIN_SEC, LINE_MAX_SEC = 0.8, 8.0
MIN_VOICED_FRACTION = 0.35
# refrão a mais: mínimo de palavras seguidas sem linha e de casamentos na letra
REPEAT_MIN_WORDS = 4
REPEAT_MIN_MATCHES = 3
REPEAT_MIN_FRACTION = 0.5
MAX_REPEAT_ROUNDS = 12


@dataclass
class Anchor:
    line: int             # índice da linha na letra
    start: float
    end: float
    matched: int = 0      # palavras da linha casadas com a transcrição
    total: int = 0
    kind: str = "match"   # "match" | "interp" | "repeat"


@dataclass
class StructurePlan:
    anchors: list[Anchor] = field(default_factory=list)   # em ordem de tempo
    dropped: list[int] = field(default_factory=list)      # linhas que este áudio não canta
    matched_words: int = 0
    total_words: int = 0

    @property
    def coverage(self) -> float:
        """Fração das palavras da letra casadas com a transcrição."""
        return self.matched_words / self.total_words if self.total_words else 0.0

    def starts(self) -> list[float]:
        return [a.start for a in self.anchors]


def _norm(word: str, language: str) -> str:
    if is_japanese(language):
        return ja_reading(word)
    return re.sub(r"[^a-z0-9']", "", unidecode(word or "").lower())


def tokenize_lines(lines: list[str], language: str) -> tuple[list[str], list[int]]:
    """Palavras normalizadas da letra e a linha de cada uma."""
    tokens, owner = [], []
    for idx, line in enumerate(lines):
        for raw in split_words(line, language):
            norm = _norm(raw, language)
            if norm:
                tokens.append(norm)
                owner.append(idx)
    return tokens, owner


def _scores(sim: np.ndarray) -> np.ndarray:
    return np.where(sim >= SIM_FULL, SCORE_FULL, np.where(sim >= SIM_PARTIAL, SCORE_PARTIAL, SCORE_MISMATCH))


def align_tokens(sim: np.ndarray) -> list[tuple[int, int]]:
    """Pares (letra, transcrição) casados, em ordem. Pontas da transcrição são livres.

    `sim`: matriz n×m de similaridade (0–100). Recorrência por linha vetorizada:
    H[i, j] = max(D[j], H[i, j-1] + GAP_TRANSCRIPT) vira um máximo acumulado.
    """
    n, m = sim.shape
    if n == 0 or m == 0:
        return []
    score = _scores(sim)
    H = np.zeros((n + 1, m + 1))
    ptr = np.zeros((n + 1, m + 1), dtype=np.int8)   # 0 diagonal, 1 pula letra, 2 pula transcrição
    H[1:, 0] = GAP_LYRIC * np.arange(1, n + 1)
    ptr[1:, 0] = 1
    ptr[0, 1:] = 2
    cols = np.arange(m + 1)
    for i in range(1, n + 1):
        diag = np.full(m + 1, -np.inf)
        diag[1:] = H[i - 1, :-1] + score[i - 1]
        up = H[i - 1] + GAP_LYRIC
        D = np.maximum(diag, up)
        choice = np.where(diag >= up, 0, 1).astype(np.int8)
        acc = np.maximum.accumulate(D - GAP_TRANSCRIPT * cols) + GAP_TRANSCRIPT * cols
        H[i] = acc
        ptr[i] = np.where(acc > D + 1e-9, 2, choice)
    i, j = n, int(np.argmax(H[n]))
    pairs = []
    while i > 0 and j > 0:
        p = ptr[i, j]
        if p == 0:
            if sim[i - 1, j - 1] >= SIM_PARTIAL:
                pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif p == 1:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def local_align(sim: np.ndarray) -> list[tuple[int, int]]:
    """Melhor trecho em comum (Smith-Waterman) entre letra (linhas de `sim`) e um pedaço da transcrição.

    Mesma recorrência vetorizada do `align_tokens`, com piso 0 (começo livre).
    """
    n, m = sim.shape
    if n == 0 or m == 0:
        return []
    score = _scores(sim)
    H = np.zeros((n + 1, m + 1))
    ptr = np.full((n + 1, m + 1), 3, dtype=np.int8)   # 0 diagonal, 1 pula letra, 2 pula transcrição, 3 início
    cols = np.arange(m + 1)
    for i in range(1, n + 1):
        diag = np.full(m + 1, -np.inf)
        diag[1:] = H[i - 1, :-1] + score[i - 1]
        up = H[i - 1] + GAP_LYRIC
        D = np.maximum(np.maximum(diag, up), 0.0)
        choice = np.where(D <= 0.0, 3, np.where(diag >= up, 0, 1)).astype(np.int8)
        acc = np.maximum.accumulate(D - GAP_TRANSCRIPT * cols) + GAP_TRANSCRIPT * cols
        H[i] = acc
        ptr[i] = np.where(acc > D + 1e-9, 2, choice)
    i, j = np.unravel_index(int(np.argmax(H)), H.shape)
    pairs = []
    while i > 0 and j > 0 and H[i, j] > 0 and ptr[i, j] != 3:
        p = ptr[i, j]
        if p == 0:
            if sim[i - 1, j - 1] >= SIM_PARTIAL:
                pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif p == 1:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def _syllables(text: str) -> int:
    from utils.lrc_realign import count_syllables

    words = re.findall(r"[a-z']+", unidecode(text or "").lower())
    return max(1, sum(count_syllables(w) for w in words))


def _est_sec(text: str) -> float:
    return min(LINE_MAX_SEC, max(LINE_MIN_SEC, _syllables(text) * SEC_PER_SYLLABLE))


def _anchors_from_pairs(pairs, owner, line_sizes, line_offsets, words, kind,
                        tokens, sim) -> tuple[dict[int, Anchor], set[int]]:
    """Âncora por linha a partir dos pares casados (só linhas com casamento suficiente).

    Devolve também as palavras da transcrição que essas âncoras usaram.
    """
    by_line: dict[int, list[tuple[int, int, int]]] = {}
    for li, tj in pairs:
        by_line.setdefault(owner[li], []).append((li - line_offsets[owner[li]], tj, li))
    out, used = {}, set()
    for line, hits in by_line.items():
        size = line_sizes[line]
        if len(hits) < min(ANCHOR_MIN_WORDS, size) and len(hits) / size < ANCHOR_MIN_FRACTION:
            continue
        chars = sum(len(tokens[li]) * (1.0 if sim[li, tj] >= SIM_FULL else 0.5) for _, tj, li in hits)
        if chars < ANCHOR_MIN_CHARS:
            continue
        used.update(tj for _, tj, _ in hits)
        hits = [(k, tj) for k, tj, _ in hits]
        (k0, j0), (k1, j1) = hits[0], hits[-1]
        start = words[j0]["start"] - k0 * EDGE_WORD_SEC
        end = words[j1]["end"] + (size - 1 - k1) * EDGE_WORD_SEC
        out[line] = Anchor(line, start, max(end, start + 0.2), len(hits), size, kind)
    return out, used


def _voiced_between(t0: float, t1: float, act: np.ndarray | None, hop: float) -> np.ndarray:
    """Tempos (centro do quadro) com voz em [t0, t1]. Sem atividade: o intervalo todo."""
    if act is None or act.size == 0:
        return np.arange(t0, t1, hop) + hop / 2
    lo, hi = max(0, int(t0 / hop)), min(act.size, int(np.ceil(t1 / hop)))
    idx = np.flatnonzero(act[lo:hi]) + lo
    return idx * hop + hop / 2


def _fill_gap(lines_idx: list[int], texts: list[str], t0: float, t1: float,
              act: np.ndarray | None, hop: float,
              hints: dict[int, list[float]] | None = None) -> tuple[list[Anchor], list[int]]:
    """Linhas sem âncora no intervalo [t0, t1], pelo tempo com voz: (colocadas, fora).

    Não cabem todas: ficam as que têm pista fraca (palavra casada sem prova
    suficiente para âncora) dentro do intervalo, e as demais saem.
    """
    placed = _spread(lines_idx, texts, t0, t1, act, hop)
    if placed is not None:
        return placed, []
    keep = [i for i in lines_idx if any(t0 <= t <= t1 for t in (hints or {}).get(i, ()))]
    placed = _spread(keep, texts, t0, t1, act, hop) if keep else None
    if placed is None:
        return [], list(lines_idx)
    return placed, [i for i in lines_idx if i not in keep]


def _trim_neighbor_voice(voiced: np.ndarray, t0: float, t1: float, hop: float, min_keep: float) -> np.ndarray:
    """Tira a voz que encosta nas pontas do intervalo (cauda da linha anterior,
    começo da seguinte), se ainda sobrar `min_keep` segundos de voz no meio."""
    if voiced.size < 2:
        return voiced
    runs = np.split(voiced, np.flatnonzero(np.diff(voiced) > 1.5 * hop) + 1)
    if len(runs) > 1 and runs[0][0] - t0 <= hop:
        runs = runs[1:]
    if len(runs) > 1 and t1 - runs[-1][-1] <= hop:
        runs = runs[:-1]
    inner = np.concatenate(runs)
    return inner if inner.size * hop >= min_keep else voiced


def _spread(lines_idx: list[int], texts: list[str], t0: float, t1: float,
            act: np.ndarray | None, hop: float) -> list[Anchor] | None:
    need = [_est_sec(texts[i]) for i in lines_idx]
    voiced = _trim_neighbor_voice(_voiced_between(t0, t1, act, hop), t0, t1, hop, MIN_VOICED_FRACTION * sum(need))
    if voiced.size * hop < MIN_VOICED_FRACTION * sum(need):
        return None
    # cada linha pega uma fatia proporcional do tempo com voz (não da pausa instrumental)
    cuts = np.cumsum([0.0] + need) / sum(need) * (voiced.size - 1)
    out = []
    for k, line in enumerate(lines_idx):
        a = float(voiced[int(round(cuts[k]))]) - hop / 2
        b = float(voiced[int(round(cuts[k + 1]))]) + hop / 2
        out.append(Anchor(line, a, max(b, a + 0.3), 0, 0, "interp"))
    return out


def build_plan(lines: list[str], words: list[dict], language: str, audio_duration: float,
               act: np.ndarray | None = None, hop: float = 0.05) -> StructurePlan | None:
    """Plano de linhas para este áudio. None quando a transcrição não serve de régua.

    `words`: palavras do Whisper ({"word", "start", "end"}) do stem de voz inteiro.
    `act`: atividade da voz por quadro de `hop` s (`utils.lrc_fit.vocal_activity`).
    """
    tokens, owner = tokenize_lines(lines, language)
    # japonês: o Whisper devolve pedaços de 1–3 caracteres e a letra está em unidades
    # (bunsetsu); sem regrupar nada casava (9% das palavras em "bloom", 3 de 35 linhas)
    words = regroup_timed_words(words, language)
    heard = [w for w in words if _norm(w.get("word", ""), language)]
    if not tokens or len(heard) < 5:
        return None
    heard_tokens = [_norm(w["word"], language) for w in heard]
    sim = cdist(tokens, heard_tokens, scorer=fuzz.ratio).astype(np.float32)

    line_sizes = [0] * len(lines)
    for o in owner:
        line_sizes[o] += 1
    line_offsets = [0] * len(lines)
    acc = 0
    for i, size in enumerate(line_sizes):
        line_offsets[i] = acc
        acc += size

    pairs = align_tokens(sim)
    anchors, used_heard = _anchors_from_pairs(pairs, owner, line_sizes, line_offsets, heard, "match", tokens, sim)
    # pista fraca: palavra casada de linha que não virou âncora
    hints: dict[int, list[float]] = {}
    for li, tj in pairs:
        if owner[li] not in anchors and len(tokens[li]) >= HINT_MIN_CHARS and sim[li, tj] >= SIM_FULL:
            hints.setdefault(owner[li], []).append(heard[tj]["start"])

    # ordem das âncoras = ordem da letra; tempo não pode voltar
    matched_list: list[Anchor] = []
    for line in sorted(anchors):
        a = anchors[line]
        if matched_list and a.start < matched_list[-1].end:
            a.start = min(max(a.start, matched_list[-1].end), a.end - 0.2)
        matched_list.append(a)

    # refrão a mais: transcrição fora das linhas ancoradas, procurada na letra inteira
    repeats: list[Anchor] = []
    failed_runs: set[tuple[int, ...]] = set()   # trecho que não casou não muda entre rodadas
    for _ in range(MAX_REPEAT_ROUNDS):
        spans = [(a.start, a.end) for a in matched_list + repeats]
        free = [j for j, w in enumerate(heard)
                if j not in used_heard and not any(s - 0.2 <= w["start"] <= e + 0.2 for s, e in spans)]
        runs, cur = [], []
        for j in free:
            if cur and j != cur[-1] + 1:
                runs.append(cur)
                cur = []
            cur.append(j)
        if cur:
            runs.append(cur)
        added = False
        for run in sorted((r for r in runs if len(r) >= REPEAT_MIN_WORDS), key=len, reverse=True):
            if tuple(run) in failed_runs:
                continue
            local = local_align(sim[:, run])
            if len(local) < max(REPEAT_MIN_MATCHES, REPEAT_MIN_FRACTION * len(run)):
                failed_runs.add(tuple(run))
                continue
            new, used = _anchors_from_pairs([(li, run[tj]) for li, tj in local], owner, line_sizes,
                                            line_offsets, heard, "repeat", tokens, sim)
            if not new:
                failed_runs.add(tuple(run))
                continue
            used_heard |= used
            repeats.extend(new.values())
            added = True
            break
        if not added:
            break

    # linhas sem âncora entre as vizinhas ancoradas, pelo tempo com voz (fora das repetições)
    if repeats:
        act = (np.ones(int(np.ceil(audio_duration / hop)) + 1, dtype=bool) if act is None else act.copy())
        for r in repeats:
            act[max(0, int(r.start / hop)):int(np.ceil(r.end / hop))] = False
    dropped = []
    result: list[Anchor] = list(repeats)
    pending: list[int] = []
    prev_end = 0.0
    anchored = {a.line: a for a in matched_list}
    for line in range(len(lines)):
        if line_sizes[line] == 0:
            continue  # linha só com pontuação
        if line not in anchored:
            pending.append(line)
            continue
        if pending:
            filled, out = _fill_gap(pending, lines, prev_end, anchored[line].start, act, hop, hints)
            result.extend(filled)
            dropped.extend(out)
            pending = []
        result.append(anchored[line])
        prev_end = anchored[line].end
    if pending:
        filled, out = _fill_gap(pending, lines, prev_end, audio_duration, act, hop, hints)
        result.extend(filled)
        dropped.extend(out)

    result.sort(key=lambda a: a.start)
    for prev, cur in zip(result, result[1:]):
        if cur.start < prev.end:
            prev.end = max(prev.start + 0.2, cur.start)
    matched = sum(a.matched for a in result if a.kind != "repeat")
    plan = StructurePlan(result, sorted(set(dropped)), matched, len(tokens))
    logger.info(
        "[ESTRUTURA] %d linhas: %d ancoradas, %d interpoladas, %d repetidas, %d fora (%s); %.0f%% das palavras casadas",
        len(lines), sum(a.kind == "match" for a in result), sum(a.kind == "interp" for a in result),
        sum(a.kind == "repeat" for a in result), len(plan.dropped),
        ", ".join(str(i + 1) for i in plan.dropped) or "nenhuma", 100 * plan.coverage,
    )
    return plan


def agreement(plan: StructurePlan, lrc_starts: list[float], tolerance: float = 1.5) -> float:
    """Fração das linhas do plano (sem repetidas) cujo início bate com o LRC na mesma linha."""
    own = [a for a in plan.anchors if a.kind == "match"]
    if not own:
        return 0.0
    ok = sum(1 for a in own if a.line < len(lrc_starts) and abs(lrc_starts[a.line] - a.start) <= tolerance)
    return ok / len(own)


def plan_to_lrc(plan: StructurePlan, lines: list[str]) -> str:
    """LRC de linha a partir do plano, com marca de pausa entre linhas afastadas."""
    from utils.lrc_fit import _format

    out = []
    for k, a in enumerate(plan.anchors):
        out.append(f"{_format(a.start)}{lines[a.line]}")
        nxt = plan.anchors[k + 1].start if k + 1 < len(plan.anchors) else None
        if nxt is None or nxt - a.end > 0.6:
            out.append(_format(a.end))
    return "\n".join(out)
