"""LRC certo para ESTE áudio: encaixe global + estrutura, e a escolha entre eles.

    LRC (LRCLIB, outra versão?) ──> lrc_fit: escala + offset pela voz do stem
    letra + Whisper do stem      ──> lrc_structure: onde cada linha foi cantada
                                 ──> concordam? fica o LRC (tempos feitos à mão)
                                     discordam e a estrutura tem prova? fica o plano

O LRC do LRCLIB é melhor que o Whisper quando é da mesma versão: os tempos foram
marcados por gente. Por isso o plano só vence quando a concordância entre os dois
é baixa e o plano casou palavras suficientes. Sem LRC, o plano é a única régua.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from utils.lrc_fit import HOP_SEC, Fit, fit_lrc, vocal_activity
from utils.lrc_pro import parse_synced_lrc
from utils.lrc_structure import StructurePlan, agreement, build_plan, plan_to_lrc, tokenize_lines

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
# linhas do plano que precisam bater com o LRC para ele ficar
MIN_AGREEMENT = 0.6
# prova mínima do plano para substituir o LRC (ou para existir sem LRC)
PLAN_MIN_COVERAGE = 0.35
PLAN_MIN_ANCHORED = 0.5

# transcribe(audio 16 kHz) -> [{"word", "start", "end"}]
TranscribeFn = Callable[[np.ndarray], list[dict]]


@dataclass
class SyncResult:
    lrc_text: str | None          # LRC escolhido (None: nada confiável)
    method: str                   # "lrc" | "lrc+encaixe" | "estrutura" | "nenhum"
    fit: Fit | None = None
    plan: StructurePlan | None = None
    agreement: float | None = None
    alternative: str | None = None  # o outro candidato, para quem puder comparar (MMS_FA)
    notes: list[str] = field(default_factory=list)


def _plan_ok(plan: StructurePlan | None, n_lines: int) -> bool:
    if plan is None or not plan.anchors:
        return False
    anchored = sum(a.kind == "match" for a in plan.anchors)
    return plan.coverage >= PLAN_MIN_COVERAGE and anchored >= PLAN_MIN_ANCHORED * max(1, n_lines - len(plan.dropped))


def _lines_with_words(texts: list[str], language: str) -> int:
    """Linhas com alguma palavra (linha só com "♪" o plano nem considera)."""
    return len(set(tokenize_lines(texts, language)[1]))


def transcribe_words(transcribe: TranscribeFn | None, audio: np.ndarray) -> list[dict] | None:
    if transcribe is None:
        return None
    try:
        return transcribe(audio)
    except Exception as e:
        logger.warning(f"[LRC SYNC] transcrição para a estrutura falhou: {e}")
        return None


def sync_lrc(lrc_text: str | None, plain_lyrics: str | None, audio: np.ndarray, language: str,
             transcribe: TranscribeFn | None = None, words: list[dict] | None = None) -> SyncResult:
    """LRC para `audio` (stem de voz, 16 kHz). `words` evita transcrever de novo."""
    duration = len(audio) / SAMPLE_RATE
    act = vocal_activity(audio, SAMPLE_RATE)
    fitted, fit = (fit_lrc(lrc_text, audio, SAMPLE_RATE) if lrc_text else (None, None))
    lrc_lines = parse_synced_lrc(fitted) if fitted else []
    if fitted and len(lrc_lines) < 3:
        fitted, lrc_lines = None, []

    texts = [ln["text"] for ln in lrc_lines]
    if not texts and plain_lyrics:
        texts = [ln.strip() for ln in plain_lyrics.splitlines()
                 if ln.strip() and not (ln.strip().startswith("[") and "]" in ln)]
    if words is None and texts:
        words = transcribe_words(transcribe, audio)
    plan = build_plan(texts, words, language, duration, act, HOP_SEC) if (texts and words) else None
    method_lrc = "lrc+encaixe" if fit and fit.applied else "lrc"

    if fitted:
        if plan is None:
            return SyncResult(fitted, method_lrc, fit, None, None, None, ["sem transcrição: só o encaixe"])
        agree = agreement(plan, [ln["start"] for ln in lrc_lines])
        plan_text = plan_to_lrc(plan, texts)
        if agree >= MIN_AGREEMENT or not _plan_ok(plan, _lines_with_words(texts, language)):
            logger.info("[LRC SYNC] LRC mantido (concordância %.0f%% com a estrutura)", 100 * agree)
            return SyncResult(fitted, method_lrc, fit, plan, agree, plan_text if _plan_ok(plan, _lines_with_words(texts, language)) else None)
        logger.info("[LRC SYNC] LRC de outra estrutura (concordância %.0f%%): plano da transcrição, "
                    "%d linhas fora, %d repetidas", 100 * agree, len(plan.dropped),
                    sum(a.kind == "repeat" for a in plan.anchors))
        return SyncResult(plan_text, "estrutura", fit, plan, agree, fitted)

    if _plan_ok(plan, _lines_with_words(texts, language)):
        return SyncResult(plan_to_lrc(plan, texts), "estrutura", None, plan)
    return SyncResult(None, "nenhum", None, plan)


def uncovered_voice(segments: list[dict], act: np.ndarray, hop: float = HOP_SEC) -> float:
    """Fração dos quadros com voz fora de qualquer verso (letra faltando no palco)."""
    if act.size == 0 or not act.any():
        return 0.0
    covered = np.zeros(act.size, dtype=bool)
    for seg in segments:
        lo = max(0, int(float(seg.get("sing_start", 0.0)) / hop))
        hi = min(act.size, int(np.ceil(float(seg.get("sing_end", 0.0)) / hop)))
        covered[lo:hi] = True
    return float((act & ~covered).sum()) / float(act.sum())
