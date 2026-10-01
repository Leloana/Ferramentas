"""Encaixe global do LRC no áudio: `t' = escala · t + offset`.

O LRC do LRCLIB vem de uma versão da música, o áudio do YouTube pode ser outra:
intro mais longa, outra mixagem, andamento um pouco diferente. As linhas
continuam na ordem certa, só deslocadas (offset) ou esticadas (escala).

A régua é a voz do stem separado: quadro "cantando" = RMS acima de
ACTIVE_REL_DB do percentil 95. Cada linha do LRC diz quando deveria haver voz
(do início até a marca de fim, a próxima linha ou a duração estimada pelas
sílabas). Para cada escala da grade, a correlação dá o melhor offset. A nota é
o F1 entre "deveria cantar" e "está cantando". Só troca quando o ganho passa de
MIN_F1_GAIN: na dúvida o LRC fica como veio.

Diferença de estrutura (refrão a mais, verso cortado) não é afim: isso é do
`utils/lrc_structure.py`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
HOP_SEC = 0.05
ACTIVE_REL_DB = -25.0
# buracos de voz menores que isso (respiração, consoante) contam como cantando
FILL_GAP_SEC = 0.3
SCALE_MIN, SCALE_MAX, SCALE_STEP = 0.92, 1.08, 0.002
MAX_OFFSET_SEC = 60.0
# duração de uma linha sem marca de fim: sílabas × isso, entre os limites
SEC_PER_SYLLABLE = 0.28
LINE_MIN_SEC, LINE_MAX_SEC = 0.8, 8.0
# ganho de F1 para aceitar o encaixe, e o desempate a favor do LRC como veio
MIN_F1_GAIN = 0.05
OFFSET_COST_PER_SEC = 0.0005
SCALE_COST = 0.2
# abaixo disso de mudança é o próprio LRC
NOOP_OFFSET_SEC = 0.1
NOOP_SCALE = 0.002

_STAMP_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_OFFSET_RE = re.compile(r"^\[offset:\s*([+-]?\d+)\]\s*$", re.IGNORECASE)


@dataclass
class Fit:
    scale: float = 1.0
    offset: float = 0.0
    f1: float = 0.0          # F1 com o encaixe
    f1_before: float = 0.0   # F1 do LRC como veio
    applied: bool = False

    def map(self, t: float) -> float:
        return max(0.0, self.scale * t + self.offset)


def vocal_activity(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Quadros de HOP_SEC com voz (bool), com buracos curtos preenchidos."""
    from utils.alignment_quality import rms_frames

    rms = rms_frames(audio, sample_rate, HOP_SEC)
    if rms.size == 0:
        return np.zeros(0, dtype=bool)
    ref = float(np.percentile(rms, 95))
    if ref <= 0:
        return np.zeros(rms.size, dtype=bool)
    act = rms > ref * 10 ** (ACTIVE_REL_DB / 20)
    gap = int(round(FILL_GAP_SEC / HOP_SEC))
    idx = np.flatnonzero(act)
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= gap + 1:
            act[a:b] = True
    return act


def line_spans(starts: list[float], ends: list[float | None] | None, syllables: list[int],
               audio_duration: float) -> list[tuple[float, float]]:
    """Trecho em que cada linha do LRC deveria ter voz, no tempo do LRC."""
    spans = []
    for i, start in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else max(audio_duration, start + LINE_MAX_SEC)
        est = min(LINE_MAX_SEC, max(LINE_MIN_SEC, syllables[i] * SEC_PER_SYLLABLE))
        end = start + est
        mark = ends[i] if ends else None
        if mark is not None and mark > start:
            end = mark
        spans.append((start, max(start + 0.1, min(end, nxt))))
    return spans


def _expected(spans: list[tuple[float, float]], scale: float, n: int) -> np.ndarray:
    """Quadros "deveria cantar" com a escala aplicada (sem offset), até n quadros."""
    e = np.zeros(n, dtype=np.float32)
    for s, t in spans:
        lo, hi = int(round(scale * s / HOP_SEC)), int(round(scale * t / HOP_SEC))
        lo, hi = max(0, lo), min(n, max(hi, lo + 1))
        e[lo:hi] = 1.0
    return e


def _f1_by_offset(e: np.ndarray, act: np.ndarray, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    """F1 de `e` deslocado por cada lag em [−max_lag, max_lag] contra `act` (via FFT)."""
    n = len(act) + len(e)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(act.astype(np.float32), size) * np.conj(np.fft.rfft(e, size)), size)
    lags = np.arange(-max_lag, max_lag + 1)
    hits = np.clip(np.round(corr[lags % size]), 0, None)
    # quadros de `e` que caem fora do áudio continuam contando como "deveria cantar"
    denom = float(e.sum()) + float(act.sum())
    return lags, 2.0 * hits / max(1.0, denom)


def fit_lines(spans: list[tuple[float, float]], act: np.ndarray) -> Fit:
    """Melhor (escala, offset) para as linhas do LRC sobre a atividade da voz."""
    if not spans or act.size == 0 or not act.any():
        return Fit()
    max_lag = int(min(MAX_OFFSET_SEC, act.size * HOP_SEC / 2) / HOP_SEC)
    last = max(t for _, t in spans)
    n = max(act.size, int(np.ceil(last * SCALE_MAX / HOP_SEC)) + 1)

    def f1_at(scale: float, lag: int) -> float:
        e = _expected(spans, scale, n)
        shifted = np.zeros(act.size, dtype=np.float32)
        if lag >= 0:
            shifted[lag:] = e[:max(0, act.size - lag)]
        else:
            shifted[:max(0, min(act.size, n + lag))] = e[-lag:-lag + act.size]
        hits = float((shifted * act).sum())
        return 2.0 * hits / max(1.0, float(e.sum()) + float(act.sum()))

    before = f1_at(1.0, 0)
    best = (before, 1.0, 0, before)
    for scale in np.arange(SCALE_MIN, SCALE_MAX + SCALE_STEP / 2, SCALE_STEP):
        lags, f1 = _f1_by_offset(_expected(spans, float(scale), n), act, max_lag)
        cost = f1 - OFFSET_COST_PER_SEC * np.abs(lags) * HOP_SEC - SCALE_COST * abs(scale - 1.0)
        k = int(np.argmax(cost))
        if cost[k] > best[0]:
            best = (float(cost[k]), float(scale), int(lags[k]), float(f1[k]))
    _, scale, lag, f1 = best
    fit = Fit(scale=round(scale, 4), offset=round(lag * HOP_SEC, 3), f1=round(f1, 3), f1_before=round(before, 3))
    moved = abs(fit.offset) >= NOOP_OFFSET_SEC or abs(fit.scale - 1.0) >= NOOP_SCALE
    fit.applied = moved and fit.f1 - fit.f1_before >= MIN_F1_GAIN
    if not fit.applied:
        fit.scale, fit.offset, fit.f1 = 1.0, 0.0, fit.f1_before
    return fit


def _syllables(text: str) -> int:
    from unidecode import unidecode

    from utils.lrc_realign import count_syllables

    words = re.findall(r"[a-z']+", unidecode(text or "").lower())
    return max(1, sum(count_syllables(w) for w in words))


def fit_lrc(lrc_text: str, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> tuple[str, Fit]:
    """LRC encaixado no stem de voz `audio`. Sem ganho claro devolve o texto intacto."""
    from utils.lrc_pro import parse_synced_lrc

    lines = parse_synced_lrc(lrc_text)
    if len(lines) < 3:
        return lrc_text, Fit()
    duration = len(audio) / sample_rate
    spans = line_spans([ln["start"] for ln in lines], [ln["end"] for ln in lines],
                       [_syllables(ln["text"]) for ln in lines], duration)
    fit = fit_lines(spans, vocal_activity(audio, sample_rate))
    logger.info("[LRC FIT] escala %.4f, offset %+.2fs, F1 %.3f → %.3f (%s)", fit.scale, fit.offset,
                fit.f1_before, fit.f1, "aplicado" if fit.applied else "LRC mantido")
    if not fit.applied:
        return lrc_text, fit
    return remap_lrc(lrc_text, fit.map), fit


def _format(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"[{cs // 6000:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}]"


def remap_lrc(lrc_text: str, fn) -> str:
    """Aplica `fn` a toda marca de tempo do LRC. O `[offset:]` entra na conta e sai do texto."""
    offset = 0.0
    for raw in (lrc_text or "").splitlines():
        m = _OFFSET_RE.match(raw.strip())
        if m:
            offset = float(m.group(1)) / 1000.0
    out = []
    for raw in (lrc_text or "").splitlines():
        if _OFFSET_RE.match(raw.strip()):
            continue
        line = raw.strip()
        stamps = ""
        while True:
            m = _STAMP_RE.match(line)
            if not m:
                break
            # mesmo corte em 0 do parse_synced_lrc, que é onde o encaixe foi medido
            stamps += _format(fn(max(0.0, int(m.group(1)) * 60 + float(m.group(2)) + offset)))
            line = line[m.end():]
        out.append(stamps + line if stamps else raw)
    return "\n".join(out)
