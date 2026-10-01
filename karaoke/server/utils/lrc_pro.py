"""Alinhamento forçado (Forced Alignment) da letra com o stem de voz, via torchaudio MMS_FA.

Dois caminhos:

- **Com LRC sincronizado** (inícios de linha): cada linha é alinhada só dentro da
  sua janela `[início − PRE_SEC, próximo início + POST_SEC]` (≤ MAX_WINDOW_SEC).
  Antes o MMS_FA rodava na música inteira de uma vez: a memória cresce com o
  quadrado da duração, estourava e o pipeline caía num fallback ruim. Linha cuja
  janela falha vira proporcional às sílabas dentro da janela (nunca espalhada
  pela pausa instrumental seguinte).
- **Sem LRC**: a letra inteira de uma vez, como antes.

Nos dois, cada palavra ganha `confidence` (média das probabilidades dos tokens,
`TokenSpan.score`, ponderada pela duração) e cada verso ganha `confidence` e
`align` ("window" | "fallback" | "global"). `utils/alignment_quality.assess` usa
isso para marcar a música para revisão.

O alinhador é injetável (`align_fn`): os testes simulam a emissão sem o modelo.
"""
from __future__ import annotations

import copy
import logging
import math
import re
from typing import Callable

import numpy as np
from unidecode import unidecode

from lyrics_text import is_japanese, ja_reading, join_words, split_words

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
PRE_SEC = 1.0
POST_SEC = 0.5
MAX_WINDOW_SEC = 30.0
MIN_WINDOW_SEC = 0.5
# fallback por sílabas: ~0,3 s por sílaba, sem passar do fim da janela
FALLBACK_SEC_PER_SYLLABLE = 0.3

# align_fn(t0, t1, palavras_normalizadas) -> [(início, fim, confiança) | None, ...]
# em segundos absolutos da música; levanta ou devolve None se não conseguir.
AlignFn = Callable[[float, float, list[str]], "list[tuple[float, float, float] | None] | None"]

_LRC_STAMP_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_LRC_OFFSET_RE = re.compile(r"\[offset:\s*([+-]?\d+)\]", re.IGNORECASE)


def _format_timestamp(t: float) -> str:
    """Formata timestamp absoluto em [MM:SS.xx]."""
    m = int(t // 60)
    s = int(t % 60)
    ms = int((t % 1) * 100)
    return f"[{m:02d}:{s:02d}.{ms:02d}]"


def parse_and_normalize_lyrics(plain_lyrics: str, language: str = "pt") -> tuple[list[list[dict]], list[str]]:
    """
    Divide a letra plana em linhas e palavras.
    Retorna:
      - lines: lista de linhas, onde cada linha é uma lista de dicionários de palavras.
      - flat_normalized_words: lista plana de palavras normalizadas não-vazias para o tokenizer.
    """
    lines = []
    flat_normalized_words = []

    for line in plain_lyrics.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ignora tags LRC de metadados
        if line.startswith("[") and "]" in line:
            if ":" in line or line.lower().startswith("[offset"):
                continue

        words_in_line = []
        for raw_word in split_words(line, language):
            # Normalização fonética/alfabética compatível com MMS_FA vocabulary:
            # remove acentos, converte para minúsculas e mantém apenas a-z e '.
            # Japonês: leitura em romaji (unidecode daria pinyin chinês para kanji).
            if is_japanese(language):
                norm_word = ja_reading(raw_word)
            else:
                norm_word = unidecode(raw_word).lower()
                norm_word = re.sub(r"[^a-z']", "", norm_word)

            word_dict = {
                "raw": raw_word,
                "norm": norm_word,
                "start": None,
                "end": None,
                "confidence": None,
            }
            words_in_line.append(word_dict)
            if norm_word:
                flat_normalized_words.append(norm_word)

        if words_in_line:
            lines.append(words_in_line)

    return lines, flat_normalized_words


def parse_synced_lrc(lrc_text: str) -> list[dict]:
    """LRC → [{"start", "end", "text"}] das linhas com letra, em ordem de tempo.

    Aceita várias marcas na linha e `[offset:ms]`; marca vazia fecha a linha
    anterior (`end`). Linhas de metadado (`[ti:...]`) são ignoradas.
    """
    lines, end_marks = [], []
    offset = 0.0
    for raw in (lrc_text or "").splitlines():
        raw = raw.strip()
        m_off = _LRC_OFFSET_RE.match(raw)
        if m_off:
            offset = float(m_off.group(1)) / 1000.0
            continue
        stamps, rest = [], raw
        while True:
            m = _LRC_STAMP_RE.match(rest)
            if not m:
                break
            stamps.append(int(m.group(1)) * 60 + float(m.group(2)))
            rest = rest[m.end():]
        if not stamps:
            continue
        text = rest.strip()
        if text:
            lines.extend({"start": t, "end": None, "text": text} for t in stamps)
        else:
            end_marks.extend(stamps)
    lines.sort(key=lambda ln: ln["start"])
    for mark in end_marks:
        before = [ln for ln in lines if ln["start"] < mark]
        if before and before[-1]["end"] is None:
            before[-1]["end"] = mark
    for ln in lines:
        ln["start"] = max(0.0, ln["start"] + offset)
        if ln["end"] is not None:
            ln["end"] = max(0.0, ln["end"] + offset)
    return lines


def lines_for_alignment(plain_lyrics: str, synced_lrc: str | None,
                        language: str) -> tuple[list[list[dict]], list[float] | None, list[float | None] | None]:
    """Linhas da letra + inícios (e fins) do LRC, se houver um que sirva.

    Mesmo número de linhas: vale o texto da letra plana com os tempos do LRC.
    Números diferentes: vale o texto do próprio LRC (é a mesma letra, já sincronizada).
    """
    lines, _ = parse_and_normalize_lyrics(plain_lyrics or "", language)
    lrc_lines = parse_synced_lrc(synced_lrc) if synced_lrc else []
    if not lrc_lines:
        return lines, None, None
    if len(lrc_lines) != len(lines):
        logger.info(f"[MMS_FA] LRC com {len(lrc_lines)} linhas e letra com {len(lines)}: usando o texto do LRC")
        lines, _ = parse_and_normalize_lyrics("\n".join(ln["text"] for ln in lrc_lines), language)
        if len(lines) != len(lrc_lines):  # linha do LRC só com pontuação etc.
            return parse_and_normalize_lyrics(plain_lyrics or "", language)[0], None, None
    return lines, [ln["start"] for ln in lrc_lines], [ln["end"] for ln in lrc_lines]


def _syllables(word: str) -> int:
    from utils.lrc_realign import count_syllables

    return count_syllables(unidecode(word or "").lower())


def spread_by_syllables(words: list[dict], start: float, end: float) -> None:
    """Distribui as palavras em [start, end] pelo número de sílabas (confiança 0)."""
    weights = [_syllables(w["raw"]) for w in words]
    total = sum(weights) or 1
    t = start
    for w, weight in zip(words, weights):
        dur = (end - start) * weight / total
        w["start"], w["end"] = round(t, 3), round(t + dur * 0.9, 3)
        w["confidence"] = 0.0
        t += dur


def _interpolate_line(words: list[dict]) -> None:
    """Palavras sem span (norm vazio, ex.: números) entre as vizinhas alinhadas."""
    if all(w["start"] is not None for w in words):
        return
    from utils.lrc_realign import interpolate_missing_words

    flat = [{"word": w["raw"], "start": w["start"], "end": w["end"]} for w in words]
    for w, filled in zip(words, interpolate_missing_words(flat)):
        w["start"], w["end"] = filled["start"], filled["end"]


def _apply_spans(words: list[dict], spans: list) -> bool:
    """Grava os spans do alinhador nas palavras com norm. False se nada veio."""
    targets = [w for w in words if w["norm"]]
    if not spans or len(spans) != len(targets) or all(s is None for s in spans):
        return False
    for w, span in zip(targets, spans):
        if span is not None:
            w["start"], w["end"], w["confidence"] = round(span[0], 3), round(span[1], 3), round(float(span[2]), 3)
    _interpolate_line(words)
    return True


def line_window(idx: int, starts: list[float], audio_duration: float, ends: list[float | None] | None = None,
                floor: float = 0.0) -> tuple[float, float]:
    """Janela de áudio da linha `idx`: [início − PRE, próximo + POST], sem passar de MAX_WINDOW_SEC.

    `floor` (fim da última palavra da linha anterior) segura o começo, mas nunca
    depois do início da própria linha. Marca de fim no LRC encurta a janela.
    """
    start = starts[idx]
    nxt = starts[idx + 1] if idx + 1 < len(starts) else audio_duration
    t0 = max(0.0, start - PRE_SEC, min(floor, start))
    t1 = min(audio_duration, nxt + POST_SEC)
    end_mark = ends[idx] if ends else None
    if end_mark is not None and end_mark > start:
        t1 = min(t1, end_mark + POST_SEC)
    t1 = min(t1, t0 + MAX_WINDOW_SEC)
    if t1 - t0 < MIN_WINDOW_SEC:
        t1 = min(audio_duration, t0 + MIN_WINDOW_SEC)
    return t0, t1


def align_lines_windowed(lines: list[list[dict]], starts: list[float], audio_duration: float,
                         align_fn: AlignFn, ends: list[float | None] | None = None) -> list[str]:
    """Alinha linha a linha na janela do LRC. Devolve o modo de cada linha ("window" | "fallback")."""
    modes = []
    floor = 0.0
    for idx, words in enumerate(lines):
        t0, t1 = line_window(idx, starts, audio_duration, ends, floor)
        norms = [w["norm"] for w in words if w["norm"]]
        ok = False
        if norms:
            try:
                ok = _apply_spans(words, align_fn(t0, t1, norms))
            except Exception as e:
                logger.info(f"[MMS_FA] linha {idx + 1} ({t0:.1f}–{t1:.1f}s) não alinhou: {e}")
        if not ok:
            # proporcional às sílabas, a partir do início do LRC e só pelo tempo que a
            # linha plausivelmente dura (não atravessa a pausa até a próxima)
            a = max(t0, min(starts[idx], t1 - 0.2))
            limit = t1 - (POST_SEC if idx + 1 < len(starts) else 0.0)
            est = sum(_syllables(w["raw"]) for w in words) * FALLBACK_SEC_PER_SYLLABLE
            b = max(a + 0.1 * len(words), min(limit, a + max(1.0, est)))
            spread_by_syllables(words, a, b)
        modes.append("window" if ok else "fallback")
        floor = max(floor, max(w["end"] for w in words))
    return modes


def align_global(lines: list[list[dict]], audio_duration: float, align_fn: AlignFn) -> list[str]:
    """Letra inteira contra o áudio inteiro (sem LRC). Levanta se o alinhador falhar."""
    flat = [w for line in lines for w in line]
    spans = align_fn(0.0, audio_duration, [w["norm"] for w in flat if w["norm"]])
    if not spans:
        raise RuntimeError("alinhador não devolveu nada")
    targets = [w for w in flat if w["norm"]]
    for w, span in zip(targets, spans):
        if span is not None:
            w["start"], w["end"], w["confidence"] = round(span[0], 3), round(span[1], 3), round(float(span[2]), 3)

    from utils.lrc_realign import interpolate_missing_words

    items = [{"word": w["raw"], "start": w["start"], "end": w["end"]} for w in flat]
    for w, filled in zip(flat, interpolate_missing_words(items)):
        w["start"], w["end"] = filled["start"], filled["end"]
    return ["global"] * len(lines)


def _span_prob(score: float) -> float:
    """TokenSpan.score é probabilidade (0..1); se vier em log, converte."""
    score = float(score)
    if score < 0:
        score = math.exp(score)
    return min(1.0, max(0.0, score))


def spans_to_words(token_spans: list, t0: float, sec_per_frame: float) -> list[tuple[float, float, float] | None]:
    """Spans de token (por palavra) → (início, fim, confiança) absolutos.

    Confiança = média das probabilidades dos tokens ponderada pelos quadros.
    """
    out = []
    for spans in token_spans:
        if not spans:
            out.append(None)
            continue
        frames = [max(1, s.end - s.start) for s in spans]
        conf = sum(_span_prob(s.score) * f for s, f in zip(spans, frames)) / sum(frames)
        out.append((t0 + spans[0].start * sec_per_frame, t0 + spans[-1].end * sec_per_frame, conf))
    return out


def mms_align_fn(audio: np.ndarray, device=None):
    """Alinhador real (MMS_FA) sobre `audio` (16 kHz mono). Devolve (align_fn, liberar)."""
    import torch
    import torchaudio

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model().to(device)
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()

    def align(t0: float, t1: float, words: list[str]):
        lo, hi = int(t0 * SAMPLE_RATE), int(t1 * SAMPLE_RATE)
        chunk = torch.from_numpy(np.ascontiguousarray(audio[lo:hi], dtype=np.float32)).unsqueeze(0).to(device)
        with torch.inference_mode():
            emission, _ = model(chunk)
            token_spans = aligner(emission[0], tokenizer(words))
        return spans_to_words(token_spans, t0, (hi - lo) / SAMPLE_RATE / emission.size(1))

    def release():
        nonlocal model
        import gc

        model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    return align, release


def build_segments(lines: list[list[dict]], modes: list[str], audio_duration: float, language: str) -> list[dict]:
    """Linhas com tempos absolutos → segments.json (tempos das palavras relativos ao sing_start)."""
    corrected_segments = []
    num_lines = len(lines)
    for i, line_words in enumerate(lines):
        line_text = join_words([w["raw"] for w in line_words], language)
        first_word_start = line_words[0]["start"]
        last_word_end = line_words[-1]["end"]
        next_word_start = lines[i + 1][0]["start"] if i + 1 < num_lines else audio_duration

        # margem de 400 ms antes e depois, sem invadir os versos vizinhos
        prev_word_end = lines[i - 1][-1]["end"] if i > 0 else 0.0
        sing_start = max(prev_word_end, first_word_start - 0.4)
        sing_end = min(last_word_end + 0.4, next_word_start)
        if sing_start >= sing_end:
            sing_start = max(0.0, first_word_start - 0.05)
            sing_end = min(last_word_end + 0.05, next_word_start)

        timed = []
        for word in line_words:
            item = {
                "word": word["raw"],
                "expected_start": round(max(0.0, word["start"] - sing_start), 3),
                "expected_end": round(max(0.0, word["end"] - sing_start), 3),
            }
            if word.get("confidence") is not None:
                item["confidence"] = word["confidence"]
            timed.append(item)

        # monotonicidade, tempo mínimo inicial e duração mínima
        if timed:
            timed[0]["expected_start"] = max(0.05, timed[0]["expected_start"])
            if timed[0]["expected_end"] < timed[0]["expected_start"] + 0.1:
                timed[0]["expected_end"] = round(timed[0]["expected_start"] + 0.1, 3)
            for idx in range(1, len(timed)):
                min_start = round(timed[idx - 1]["expected_start"] + 0.05, 3)
                if timed[idx]["expected_start"] < min_start:
                    timed[idx]["expected_start"] = min_start
                if timed[idx]["expected_end"] < timed[idx]["expected_start"] + 0.1:
                    timed[idx]["expected_end"] = round(timed[idx]["expected_start"] + 0.1, 3)

        confs = [w["confidence"] for w in line_words if w.get("confidence") is not None]
        corrected_segments.append({
            "id": i + 1,
            "label": f"Parte {i + 1}",
            "sing_start": round(sing_start, 3),
            "sing_end": round(sing_end, 3),
            "pause_start": round(sing_end, 3),
            "pause_end": round(min(sing_end + 0.1, next_word_start), 3),
            "language": language,
            "lyrics": line_text,
            "lyrics_timed": timed,
            "confidence": round(float(np.mean(confs)), 3) if confs else None,
            "align": modes[i],
        })

    # sing_end cobre a última palavra e não invade o verso seguinte
    from utils.segment_timing import finalize_segments

    finalize_segments(corrected_segments, audio_duration)
    return corrected_segments


def segments_to_lrc(segments: list[dict]) -> str:
    lrc_lines = []
    n = len(segments)
    for i, seg in enumerate(segments):
        lrc_lines.append(f"{_format_timestamp(seg['sing_start'])}{seg['lyrics']}")
        end_t = seg["sing_end"]
        next_start = segments[i + 1]["sing_start"] if i + 1 < n else (end_t + 2.0)
        # marca de pausa se houver espaço
        if (next_start - end_t) > 0.6:
            lrc_lines.append(f"{_format_timestamp(end_t)}")
    return "\n".join(lrc_lines)


def align_lines(lines: list[list[dict]], audio_duration: float, align_fn: AlignFn,
                starts: list[float] | None = None, ends: list[float | None] | None = None) -> list[str]:
    """Janela por linha quando há inícios do LRC; senão a letra inteira de uma vez."""
    if starts:
        return align_lines_windowed(lines, starts, audio_duration, align_fn, ends)
    return align_global(lines, audio_duration, align_fn)


def align_lyrics_forced(
    vocal_audio_path: str,
    plain_lyrics: str,
    language: str = "pt",
    device: str = None,
    synced_lrc: str | None = None,
    align_fn: AlignFn | None = None,
    transcribe_fn=None,
) -> tuple[list[dict], str]:
    """Alinha a letra ao stem de voz. Devolve (segments, lrc_text).

    `synced_lrc`: LRC com os inícios das linhas (LRCLIB, revisado ou anterior) —
    ativa o alinhamento por janela. `align_fn` substitui o MMS_FA (testes).
    `transcribe_fn(audio) -> palavras do Whisper`: liga o encaixe e o plano por
    estrutura (`utils/lrc_sync`), para LRC de outra versão do áudio.
    """
    from utils.audio import load_audio_full

    logger.info(f"Carregando áudio vocal para alinhamento forçado: {vocal_audio_path}")
    audio = load_audio_full(vocal_audio_path)  # 16 kHz mono
    audio_duration = len(audio) / SAMPLE_RATE

    candidates = _sync_candidates(synced_lrc, plain_lyrics, audio, language, transcribe_fn)
    plans = [(label, lines_for_alignment(plain_lyrics, lrc, language)) for label, lrc in candidates]
    if not any(w["norm"] for _, (lines, _, _) in plans for line in lines for w in line):
        raise ValueError("A letra fornecida não contém palavras válidas para alinhamento.")

    release = None
    try:
        if align_fn is None:
            logger.info(f"Executando Forced Alignment no dispositivo: {device or 'auto'} "
                        f"({'por linha' if plans[0][1][1] else 'letra inteira'})")
            align_fn, release = mms_align_fn(audio, device)
        best = None
        for label, (lines, starts, ends) in plans:
            pristine = copy.deepcopy(lines)
            modes = align_lines(lines, audio_duration, align_fn, starts, ends)
            segments = build_segments(lines, modes, audio_duration, language)
            if starts and _looks_out_of_sync(segments):
                # LRC fora de sincronia com este áudio (LRCLIB de outra versão): as janelas
                # caem no lugar errado. Tenta a letra inteira e fica com a melhor nota.
                segments = _best_of_global(segments, pristine, audio_duration, align_fn, language)
            if len(plans) > 1:
                try:
                    quality = _selection_score(segments, audio)
                except Exception as e:
                    logger.warning(f"[MMS_FA] nota do candidato {label} falhou: {e}")
                    quality = float("-inf")
                logger.info(f"[MMS_FA] candidato {label}: nota {quality:.1f}")
                if best is None or quality > best[0]:
                    best = (quality, segments)
            else:
                best = (None, segments)
        segments = best[1]
    finally:
        if release is not None:
            logger.info("Limpando recursos e cache da GPU (Forced Alignment)...")
            release()

    fallback = sum(1 for s in segments if s.get("align") == "fallback")
    if fallback:
        logger.warning(f"[MMS_FA] {fallback}/{len(segments)} linhas sem alinhamento (tempo por sílabas)")
    return segments, segments_to_lrc(segments)


# peso da voz sem verso na escolha entre candidatos (plano tirou linha cantada)
UNCOVERED_VOICE_WEIGHT = 60.0


def _sync_candidates(synced_lrc, plain_lyrics, audio, language, transcribe_fn) -> list[tuple[str, str | None]]:
    """LRCs a alinhar: o escolhido pelo lrc_sync e a alternativa dele. Sem transcrição: o LRC como veio."""
    if transcribe_fn is None:
        return [("lrc", synced_lrc)]
    try:
        from utils.lrc_sync import sync_lrc

        res = sync_lrc(synced_lrc, plain_lyrics, audio, language, transcribe_fn)
    except Exception as e:
        logger.warning(f"[MMS_FA] encaixe/estrutura falhou ({e}); alinhando o LRC como veio")
        return [("lrc", synced_lrc)]
    out = [(res.method, res.lrc_text or synced_lrc)]
    if res.alternative:
        out.append(("lrc" if res.method == "estrutura" else "estrutura", res.alternative))
    return out


def _selection_score(segments: list[dict], audio: np.ndarray) -> float:
    """Nota para escolher entre candidatos: qualidade do alinhamento − voz sem letra."""
    from utils.alignment_quality import assess, rms_frames
    from utils.lrc_fit import HOP_SEC, vocal_activity
    from utils.lrc_sync import uncovered_voice

    duration = len(audio) / SAMPLE_RATE
    quality = assess(segments, duration, rms_frames(audio, SAMPLE_RATE))["score"]
    return quality - UNCOVERED_VOICE_WEIGHT * uncovered_voice(segments, vocal_activity(audio), HOP_SEC)


def _looks_out_of_sync(segments: list[dict]) -> bool:
    from utils.alignment_quality import LOW_CONFIDENCE

    n = max(1, len(segments))
    fallback = sum(1 for s in segments if s.get("align") == "fallback") / n
    confs = [s["confidence"] for s in segments if s.get("confidence") is not None]
    return fallback > 0.3 or (bool(confs) and float(np.median(confs)) < LOW_CONFIDENCE)


def _best_of_global(windowed: list[dict], lines: list[list[dict]], audio_duration: float,
                    align_fn: AlignFn, language: str) -> list[dict]:
    from utils.alignment_quality import assess

    try:
        modes = align_global(lines, audio_duration, align_fn)
        global_segs = build_segments(lines, modes, audio_duration, language)
    except Exception as e:
        logger.warning(f"[MMS_FA] letra inteira também falhou ({e}); mantendo o alinhamento por linha")
        return windowed
    a, b = assess(windowed, audio_duration)["score"], assess(global_segs, audio_duration)["score"]
    logger.info(f"[MMS_FA] por linha {a} × letra inteira {b}")
    return global_segs if b > a else windowed
