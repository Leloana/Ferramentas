"""Portão de qualidade do alinhamento da letra (segments.json).

`assess` dá uma nota de 0 a 100 e diz o que está errado, para a música ser
marcada "revisar" (`meta.json["needs_review"]`) em vez de ir direto para o
palco com a letra fora do tempo. Métricas:

- confiança por palavra (MMS_FA, `lyrics_timed[].confidence`): fração abaixo
  de LOW_CONFIDENCE e mediana; segmentos antigos sem confiança só usam o resto;
- estruturais: palavras empilhadas (>= 3 seguidas a menos de 60 ms), versos
  com mais de 12 s, palavras com menos de 80 ms, palavras depois do sing_end
  ou do fim do áudio, versos/palavras sobrepostos;
- com o RMS do stem de voz: fração de palavras caindo em silêncio;
- por verso: palavras espalhadas por igual (o alinhador desistiu e repartiu o
  tempo) e, com o Whisper do stem de voz (`.structure_words.json`, gravado na
  geração da letra), verso deslocado: a letra casa com o que foi cantado, mas
  em outro tempo. É o caso "transcrição boa, letra fora do lugar".

Versos com problema grave (`SEVERE_LINE_FLAGS`) marcam a música para revisar
mesmo com nota alta (>= REVIEW_SEVERE_MIN versos e >= REVIEW_SEVERE_FRAC deles):
dois versos quebrados numa música de 30 quase não mexiam na média e a música
ia para o palco assim. Conferido com 79 partidas gravadas: nos versos graves o
canto caiu 0,55 s (mediana) longe da letra contra 0,28 s nos outros, e 24%
passaram de 1 s contra 6%. `tools/audit_alignment.py` reavalia a biblioteca.

Os pesos são um primeiro chute: calibrar com músicas reais no servidor.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

REVIEW_SCORE_MIN = 70.0
REVIEW_SEVERE_MIN = 3
REVIEW_SEVERE_FRAC = 0.10
LOW_CONFIDENCE = 0.35
STACK_GAP_SEC = 0.06
STACK_MIN_RUN = 3
LONG_VERSE_SEC = 12.0
SHORT_WORD_SEC = 0.08
RMS_HOP_SEC = 0.05
# quadro "em silêncio": abaixo de −30 dB do percentil 95 do stem
SILENCE_REL_DB = -30.0

# Palavras espalhadas por igual: >= 4 palavras, passo médio >= 0,9 s e quase
# constante (desvio/média abaixo de 8%): canto de verdade não é metrônomo.
UNIFORM_MIN_WORDS = 4
UNIFORM_MIN_GAP_SEC = 0.9
UNIFORM_MAX_CV = 0.08
# Verso × Whisper do stem: procura as palavras até STEM_WINDOW_SEC antes/depois
# do verso; com >= STEM_MIN_MATCHED casadas (e >= 60% do verso), deslocado se a
# mediana do atraso passa de DISPLACED_SEC, fora do ritmo se os atrasos se espalham.
# Janela curta de propósito: com 8 s o refrão casava com a repetição seguinte
# (10% dos versos da biblioteca "deslocados" à toa). Na biblioteca o atraso
# mediano é −0,02 s: as letras certas batem com o stem quase ao centésimo.
STEM_WINDOW_SEC = 2.0
STEM_MIN_MATCHED = 3
STEM_MIN_MATCHED_FRAC = 0.6
DISPLACED_SEC = 0.8
OFF_RHYTHM_SEC = 1.2
STRUCTURE_WORDS_FILE = ".structure_words.json"
# Empilhadas viram grave ("grudadas") só quando são boa parte do verso: três
# palavras rápidas de rap passavam por empilhadas e quase toda música caía.
GLUED_MIN_FRAC = 0.4
SEVERE_LINE_FLAGS = {"espalhadas por igual", "deslocado", "fora do ritmo", "grudadas"}

# penalidade = peso × fração (0..1) de palavras/versos com o problema
WEIGHTS = {
    "low_conf": 60.0,
    "median_conf": 60.0,  # por ponto abaixo de 0,5
    "stacked": 80.0,
    "long_verse": 40.0,
    "short": 40.0,
    "past_end": 40.0,
    "overlap": 40.0,
    "silence": 60.0,
    "uniform": 60.0,
    "displaced": 80.0,
}


def rms_frames(audio: np.ndarray, sample_rate: int, hop_sec: float = RMS_HOP_SEC) -> np.ndarray:
    """RMS por quadro de `hop_sec` (sem sobreposição)."""
    hop = max(1, int(round(hop_sec * sample_rate)))
    n = len(audio) // hop
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    frames = np.asarray(audio[:n * hop], dtype=np.float32).reshape(n, hop)
    return np.sqrt(np.mean(frames * frames, axis=1))


def _flatten(segments: list[dict]) -> list[dict]:
    words = []
    for idx, seg in enumerate(segments):
        base = float(seg.get("sing_start", 0.0))
        for w in seg.get("lyrics_timed") or []:
            words.append({
                "seg": idx,
                "start": base + float(w.get("expected_start", 0.0)),
                "end": base + float(w.get("expected_end", 0.0)),
                "confidence": w.get("confidence"),
            })
    return words


def _stacked_mask(words: list[dict]) -> list[bool]:
    """Palavras em sequências de >= STACK_MIN_RUN com inícios a < STACK_GAP_SEC."""
    mask = [False] * len(words)
    run_start = 0
    for i in range(1, len(words) + 1):
        close = i < len(words) and words[i]["start"] - words[i - 1]["start"] < STACK_GAP_SEC
        if not close:
            if i - run_start >= STACK_MIN_RUN:
                for k in range(run_start, i):
                    mask[k] = True
            run_start = i
    return mask


def _silence_mask(words: list[dict], rms: np.ndarray, hop: float) -> list[bool] | None:
    rms = np.asarray(rms, dtype=np.float32)
    if rms.size == 0:
        return None
    ref = float(np.percentile(rms, 95))
    if ref <= 0:
        return None
    thr = ref * 10 ** (SILENCE_REL_DB / 20)
    out = []
    for w in words:
        lo = max(0, int(w["start"] / hop))
        hi = min(rms.size, max(lo + 1, int(np.ceil(w["end"] / hop))))
        out.append(lo < rms.size and float(rms[lo:hi].max()) < thr)
    return out


def _uniform_lines(segments: list[dict], lyric_segs: list[int]) -> list[int]:
    """Versos com as palavras repartidas em passo constante (tempo inventado)."""
    out = []
    for i in lyric_segs:
        starts = [float(w.get("expected_start", 0.0)) for w in segments[i]["lyrics_timed"]]
        if len(starts) < UNIFORM_MIN_WORDS:
            continue
        # o 1º passo costuma ser o "encaixe" do começo; os outros mostram o padrão
        gaps = np.diff(starts[1:]) if len(starts) > UNIFORM_MIN_WORDS else np.diff(starts)
        mean = float(np.mean(gaps))
        if mean >= UNIFORM_MIN_GAP_SEC and float(np.std(gaps)) / mean < UNIFORM_MAX_CV:
            out.append(i)
    return out


def stem_line_offsets(segments: list[dict], lyric_segs: list[int], stem_words: list[dict]) -> dict[int, dict]:
    """Por verso: {"matched", "offset", "spread"} contra o Whisper do stem de voz.

    offset = mediana de (tempo no stem - tempo na letra) das palavras casadas;
    spread = desvio absoluto mediano desses atrasos (ritmo diferente).
    """
    from utils.segment_timing import match_word_pairs

    stem = sorted((w for w in stem_words if w.get("start") is not None), key=lambda w: float(w["start"]))
    starts = np.array([float(w["start"]) for w in stem]) if stem else np.zeros(0)
    out = {}
    for i in lyric_segs:
        seg = segments[i]
        timed = seg["lyrics_timed"]
        lo = float(seg["sing_start"]) - STEM_WINDOW_SEC
        hi = float(seg["sing_end"]) + STEM_WINDOW_SEC
        a, b = int(np.searchsorted(starts, lo)), int(np.searchsorted(starts, hi))
        window = stem[a:b]
        if not window:
            continue
        pairs = match_word_pairs([w.get("word", "") for w in timed], window)
        if len(pairs) < max(STEM_MIN_MATCHED, STEM_MIN_MATCHED_FRAC * len(timed)):
            continue
        base = float(seg["sing_start"])
        deltas = np.array([float(window[j]["start"]) - (base + float(timed[k].get("expected_start", 0.0)))
                           for k, j in pairs.items()])
        median = float(np.median(deltas))
        out[i] = {"matched": len(pairs), "offset": round(median, 2),
                  "spread": round(float(np.median(np.abs(deltas - median))), 2)}
    return out


def load_stem_words(song_dir: str | Path) -> list[dict] | None:
    """Palavras do Whisper no stem de voz, do cache da geração da letra (sem GPU)."""
    path = Path(song_dir) / STRUCTURE_WORDS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("words") or None
    except Exception:
        return None


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


def assess(segments: list[dict], audio_duration: float | None = None,
           vocal_rms_frames: np.ndarray | None = None, rms_hop: float = RMS_HOP_SEC,
           stem_words: list[dict] | None = None) -> dict:
    """Nota do alinhamento: {"score", "flags", "lines": [{"idx", "confidence", "flags"}],
    "metrics", "severe_lines"}.

    `vocal_rms_frames`: RMS do stem de voz em quadros de `rms_hop` s (ver `rms_frames`).
    `stem_words`: Whisper do stem de voz (ver `load_stem_words`) para achar verso deslocado.
    """
    words = _flatten(segments)
    lyric_segs = [i for i, s in enumerate(segments) if s.get("lyrics_timed")]
    if not words:
        return {"score": 0.0, "flags": ["sem palavras com tempo"], "lines": [], "metrics": {}}

    n = len(words)
    line_flags: dict[int, set[str]] = {i: set() for i in lyric_segs}
    flags: list[str] = []
    penalty = 0.0
    metrics: dict = {"words": n, "lines": len(lyric_segs)}

    # confiança
    confs = [w["confidence"] for w in words if w["confidence"] is not None]
    if confs:
        low = sum(c < LOW_CONFIDENCE for c in confs) / len(confs)
        median = float(np.median(confs))
        metrics.update(low_confidence=round(low, 3), median_confidence=round(median, 3))
        penalty += WEIGHTS["low_conf"] * low + WEIGHTS["median_conf"] * max(0.0, 0.5 - median)
        if low >= 0.1:
            flags.append(f"confiança baixa em {_pct(low)} das palavras")

    def add(key: str, mask: list[bool], line_flag: str, msg: str, weight_key: str | None = None) -> None:
        nonlocal penalty
        count = sum(mask)
        frac = count / n
        metrics[key] = count
        penalty += WEIGHTS[weight_key or key] * frac
        if count:
            flags.append(msg.format(n=count, pct=_pct(frac)))
            for w, bad in zip(words, mask):
                if bad and w["seg"] in line_flags:
                    line_flags[w["seg"]].add(line_flag)

    stacked = _stacked_mask(words)
    add("stacked", stacked, "empilhadas", "palavras empilhadas ({n})")
    per_line: dict[int, list[bool]] = {}
    for w, bad in zip(words, stacked):
        per_line.setdefault(w["seg"], []).append(bad)
    for i, marks in per_line.items():
        if i in line_flags and sum(marks) >= STACK_MIN_RUN and sum(marks) >= GLUED_MIN_FRAC * len(marks):
            line_flags[i].add("grudadas")
    add("short", [w["end"] - w["start"] < SHORT_WORD_SEC for w in words], "palavras curtas",
        "palavras com menos de 80 ms ({n})")
    past = []
    for w in words:
        seg = segments[w["seg"]]
        beyond_verse = w["end"] > float(seg.get("sing_end", w["end"])) + 0.01
        beyond_audio = audio_duration is not None and w["end"] > audio_duration + 0.01
        past.append(beyond_verse or beyond_audio)
    add("past_end", past, "fora do verso", "palavras depois do fim do verso ({n})")
    if vocal_rms_frames is not None:
        silent = _silence_mask(words, vocal_rms_frames, rms_hop)
        if silent is not None:
            add("silence", silent, "no silêncio", "{pct} das palavras no silêncio da voz")

    # versos longos e sobrepostos (fração sobre os versos com letra)
    n_lines = max(1, len(lyric_segs))
    long_lines = [i for i in lyric_segs if segments[i]["sing_end"] - segments[i]["sing_start"] > LONG_VERSE_SEC]
    metrics["long_verses"] = len(long_lines)
    penalty += WEIGHTS["long_verse"] * len(long_lines) / n_lines
    if long_lines:
        flags.append(f"versos com mais de 12 s ({len(long_lines)})")
    for i in long_lines:
        line_flags[i].add("longo")

    overlaps = set()
    for a, b in zip(range(len(segments)), range(1, len(segments))):
        sa, sb = segments[a], segments[b]
        if sa["sing_end"] > sb["sing_start"] + 0.001:
            overlaps.update((a, b))
    for prev, cur in zip(words, words[1:]):
        if prev["seg"] != cur["seg"] and prev["end"] > cur["start"] + 0.001:
            overlaps.update((prev["seg"], cur["seg"]))
    overlaps &= set(lyric_segs)
    metrics["overlaps"] = len(overlaps)
    penalty += WEIGHTS["overlap"] * len(overlaps) / n_lines
    if overlaps:
        flags.append(f"versos sobrepostos ({len(overlaps)})")
    for i in overlaps:
        line_flags[i].add("sobreposto")

    uniform = _uniform_lines(segments, lyric_segs)
    metrics["uniform_lines"] = len(uniform)
    penalty += WEIGHTS["uniform"] * len(uniform) / n_lines
    if uniform:
        flags.append(f"versos com palavras espalhadas por igual ({len(uniform)})")
    for i in uniform:
        line_flags[i].add("espalhadas por igual")

    offsets = stem_line_offsets(segments, lyric_segs, stem_words) if stem_words else {}
    displaced = []
    for i, o in offsets.items():
        if abs(o["offset"]) > DISPLACED_SEC:
            line_flags[i].add("deslocado")
            displaced.append(i)
        elif o["spread"] > OFF_RHYTHM_SEC:
            line_flags[i].add("fora do ritmo")
            displaced.append(i)
    if stem_words:
        metrics["stem_checked_lines"] = len(offsets)
        metrics["displaced_lines"] = len(displaced)
        penalty += WEIGHTS["displaced"] * len(displaced) / n_lines
        if displaced:
            flags.append(f"versos fora do tempo do canto ({len(displaced)})")

    lines = []
    for i in lyric_segs:
        seg = segments[i]
        conf = seg.get("confidence")
        if conf is None:
            wc = [w.get("confidence") for w in seg["lyrics_timed"] if w.get("confidence") is not None]
            conf = round(float(np.mean(wc)), 3) if wc else None
        if conf is not None and conf < LOW_CONFIDENCE:
            line_flags[i].add("confiança baixa")
        if seg.get("align") == "fallback":
            line_flags[i].add("sem alinhamento")
        line = {"idx": i, "confidence": conf, "flags": sorted(line_flags[i])}
        if i in offsets:
            line["stem_offset"] = offsets[i]["offset"]
        lines.append(line)

    fallback = sum(1 for s in segments if s.get("align") == "fallback")
    if fallback:
        flags.append(f"versos sem alinhamento, tempo estimado ({fallback})")

    score = round(max(0.0, min(100.0, 100.0 - penalty)), 1)
    severe = [ln["idx"] for ln in lines if SEVERE_LINE_FLAGS.intersection(ln["flags"])]
    return {"score": score, "flags": flags, "lines": lines, "metrics": metrics, "severe_lines": severe}


def needs_review(quality: dict) -> bool:
    """Nota baixa ou versos graves demais (quantidade e fração)."""
    severe = len(quality.get("severe_lines") or [])
    lines = max(1, len(quality.get("lines") or []))
    return (quality["score"] < REVIEW_SCORE_MIN
            or (severe >= REVIEW_SEVERE_MIN and severe / lines >= REVIEW_SEVERE_FRAC))


def record_alignment_quality(song_dir: str | Path, segments: list[dict] | None = None,
                             audio_duration: float | None = None, vocal_audio: np.ndarray | None = None,
                             sample_rate: int = 16000) -> dict | None:
    """Avalia o segments.json da música e grava em meta.json:
    `alignment_quality` (resultado do `assess`) e `needs_review` (nota < REVIEW_SCORE_MIN).

    Sem `vocal_audio` tenta carregar o vocal.mp3 (para o teste de silêncio).
    Nunca levanta: é diagnóstico, não pode derrubar o pipeline.
    """
    song_dir = Path(song_dir)
    try:
        if segments is None:
            segments = json.loads((song_dir / "segments.json").read_text(encoding="utf-8"))
        if vocal_audio is None and (song_dir / "vocal.mp3").exists():
            try:
                from utils.audio import load_audio_full

                vocal_audio = load_audio_full(song_dir / "vocal.mp3")
            except Exception as e:
                logger.debug(f"[Qualidade] vocal.mp3 não carregado: {e}")
        rms = None
        if vocal_audio is not None:
            rms = rms_frames(vocal_audio, sample_rate)
            if audio_duration is None:
                audio_duration = len(vocal_audio) / sample_rate
        quality = assess(segments, audio_duration, rms, stem_words=load_stem_words(song_dir))
        meta_path = song_dir / "meta.json"
        if not meta_path.exists():
            return quality
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["alignment_quality"] = quality
        meta["needs_review"] = needs_review(quality)
        with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(meta, f, indent=4, ensure_ascii=False)
        logger.info(f"[Qualidade] {song_dir.name}: {quality['score']} "
                    f"{'(revisar) ' if meta['needs_review'] else ''}{'; '.join(quality['flags'])}")
        return quality
    except Exception as e:
        logger.warning(f"[Qualidade] avaliação do alinhamento falhou: {e}")
        return None
