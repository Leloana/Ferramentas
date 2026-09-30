"""Análise de altura (melodia): f0 por YIN em numpy e nota de afinação por verso.

Referência: f0 do stem vocal do Demucs, salvo em songs/<slug>/pitch.json como
{"hop_sec": 0.01, "midi": [..., None, ...]} (None = sem voz no quadro).
"""
import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

PITCH_SR = 16000
HOP_SEC = 0.01
FMIN = 70.0
FMAX = 1000.0

RMS_GATE = 0.01        # quadro abaixo disso (áudio float em [-1, 1]) = sem voz
MIC_RMS_GATE = 0.003   # mic do celular é mais baixo que o stem (o gate do Whisper é 0.0018)
# Com oitava livre, altura aleatória já faz ~29 pontos: a nota mostrada parte daí
CHANCE_SCORE = 30.0
WIN = 512              # janela de integração do YIN (32 ms a 16 kHz)
CHUNK_FRAMES = 2048    # quadros por lote de FFT (limita a memória)
MEDIAN_FRAMES = 5
MIN_FRAMES = 20        # abaixo disso não há informação para dar nota
MAX_LAG_SEC = 0.25
HIT_SEMITONES = 1.0
ZERO_SEMITONES = 2.5


def _as_float(audio) -> np.ndarray:
    a = np.asarray(audio)
    if a.ndim > 1:
        a = a.mean(axis=-1) if a.shape[-1] <= 2 else a.mean(axis=0)
    if np.issubdtype(a.dtype, np.integer):
        a = a.astype(np.float32) / 32768.0
    a = np.nan_to_num(a.astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0)
    return a


def yin_f0(audio: np.ndarray, sr: int = PITCH_SR, hop_sec: float = HOP_SEC,
           fmin=FMIN, fmax=FMAX, threshold: float = 0.15,
           rms_gate: float = RMS_GATE) -> tuple[np.ndarray, np.ndarray]:
    """f0 (Hz, 0 = sem voz) e confiança 0..1 por quadro; quadro i centrado em i*hop."""
    x = _as_float(audio)
    hop = max(1, int(round(sr * hop_sec)))
    n_frames = 1 + len(x) // hop if len(x) else 0
    f0 = np.zeros(n_frames, dtype=np.float32)
    conf = np.zeros(n_frames, dtype=np.float32)
    if n_frames == 0:
        return f0, conf

    tau_min = max(2, int(np.floor(sr / fmax)))
    tau_max = int(np.ceil(sr / fmin))
    n_tau = tau_max + 2                      # d(0..tau_max+1): vizinho da parábola
    frame_len = WIN + n_tau
    nfft = 1 << int(np.ceil(np.log2(frame_len + WIN)))
    half = frame_len // 2
    xp = np.pad(x, (half, half + hop + frame_len))
    taus = np.arange(n_tau)

    for c0 in range(0, n_frames, CHUNK_FRAMES):
        idx = np.arange(c0, min(n_frames, c0 + CHUNK_FRAMES))
        frames = xp[idx[:, None] * hop + np.arange(frame_len)[None, :]].astype(np.float64)
        frames -= frames.mean(axis=1, keepdims=True)

        # d(tau) = E0 + E_tau - 2 r(tau), r pela FFT, energias por soma acumulada
        spec = np.fft.rfft(frames, nfft)
        spec_w = np.fft.rfft(frames[:, :WIN], nfft)
        r = np.fft.irfft(np.conj(spec_w) * spec, nfft)[:, :n_tau]
        cs = np.concatenate([np.zeros((len(idx), 1)), np.cumsum(frames ** 2, axis=1)], axis=1)
        e_tau = cs[:, taus + WIN] - cs[:, taus]
        d = np.maximum(e_tau[:, :1] + e_tau - 2.0 * r, 0.0)

        # diferença média acumulada normalizada
        cum = np.cumsum(d[:, 1:], axis=1)
        dn = np.ones_like(d)
        dn[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(cum, 1e-12)

        # 1º mínimo local abaixo do limiar dentro de [tau_min, tau_max]
        mid = dn[:, tau_min:tau_max + 1]
        prev = dn[:, tau_min - 1:tau_max]
        nxt = dn[:, tau_min + 1:tau_max + 2]
        cand = (mid < threshold) & (mid <= prev) & (mid < nxt)
        has = cand.any(axis=1)
        t = cand.argmax(axis=1) + tau_min

        rows = np.arange(len(idx))
        a, b, cc = dn[rows, t - 1], dn[rows, t], dn[rows, t + 1]
        den = a - 2.0 * b + cc
        shift = np.where(np.abs(den) > 1e-12, 0.5 * (a - cc) / np.where(den == 0, 1, den), 0.0)
        shift = np.clip(shift, -1.0, 1.0)
        tau_ref = t + shift

        rms = np.sqrt(e_tau[:, 0] / WIN)
        voiced = has & (rms >= rms_gate) & (tau_ref > 0)
        f0[idx] = np.where(voiced, sr / np.maximum(tau_ref, 1e-6), 0.0)
        conf[idx] = np.where(voiced, np.clip(1.0 - b, 0.0, 1.0), 0.0)
    return f0, conf


def hz_to_midi(f0) -> np.ndarray:
    f = np.asarray(f0, dtype=np.float64)
    out = np.full(f.shape, np.nan)
    ok = np.isfinite(f) & (f > 0)
    out[ok] = 69.0 + 12.0 * np.log2(f[ok] / 440.0)
    return out


def _median_voiced(midi: np.ndarray, k: int = MEDIAN_FRAMES) -> np.ndarray:
    """Mediana deslizante só entre quadros com voz (mata saltos de oitava isolados)."""
    out = midi.copy()
    voiced = np.isfinite(midi)
    if not voiced.any() or k < 2:
        return out
    pad = k // 2
    mp = np.pad(midi, pad, constant_values=np.nan)
    win = np.lib.stride_tricks.sliding_window_view(mp, k)[voiced]
    out[voiced] = np.nanmedian(win, axis=1)
    return out


def _mic_midi(audio: np.ndarray, sr: int, rms_gate: float = RMS_GATE) -> np.ndarray:
    f0, _ = yin_f0(audio, sr=sr, rms_gate=rms_gate)
    return _median_voiced(hz_to_midi(f0))


def extract_reference(vocal_audio: np.ndarray, sr=PITCH_SR) -> dict:
    midi = _mic_midi(vocal_audio, sr)
    return {"hop_sec": HOP_SEC,
            "midi": [None if not np.isfinite(v) else round(float(v), 2) for v in midi]}


def _valid_reference(ref) -> bool:
    return isinstance(ref, dict) and isinstance(ref.get("midi"), list)


def load_or_build_reference(song_dir: Path, loader) -> dict | None:
    """pitch.json da música; se não existir, gera a partir do vocal.mp3 via loader(path)."""
    try:
        song_dir = Path(song_dir)
        path = song_dir / "pitch.json"
        if path.is_file():
            try:
                ref = json.loads(path.read_text(encoding="utf-8"))
                if _valid_reference(ref):
                    return ref
                logger.warning("pitch.json inválido em %s; regerando", song_dir)
            except (OSError, ValueError) as e:
                logger.warning("pitch.json ilegível em %s (%s); regerando", song_dir, e)
        vocal = song_dir / "vocal.mp3"
        if not vocal.is_file():
            return None
        ref = extract_reference(loader(vocal), sr=PITCH_SR)
        fd, tmp = tempfile.mkstemp(dir=song_dir, prefix=".pitch.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(ref, f, separators=(",", ":"))
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return ref
    except Exception:
        logger.exception("Falha ao obter a referência de altura em %s", song_dir)
        return None


def _ref_array(reference: dict) -> tuple[np.ndarray, float]:
    midi = reference.get("midi") or []
    arr = np.array([np.nan if v is None else v for v in midi], dtype=np.float64)
    hop = float(reference.get("hop_sec") or HOP_SEC)
    return arr, hop


def verse_pitch_score(mic_audio: np.ndarray, window_start: float, reference: dict,
                      transpose_semitones: float = 0.0, sr=PITCH_SR) -> dict | None:
    """Nota de afinação do verso: distância de classe de altura (oitava livre) e folga de tempo."""
    try:
        if not _valid_reference(reference):
            return None
        mic = _mic_midi(mic_audio, sr, MIC_RMS_GATE)
        ref, ref_hop = _ref_array(reference)
        if len(mic) == 0 or len(ref) == 0 or not np.isfinite(mic).any():
            return None
        if abs(ref_hop - HOP_SEC) > 1e-9:          # referência em outro passo: reamostra
            t = np.arange(int(len(ref) * ref_hop / HOP_SEC)) * HOP_SEC
            ref = ref[np.minimum((t / ref_hop).round().astype(int), len(ref) - 1)]
        ref = ref + float(transpose_semitones or 0.0)

        n = len(mic)
        start = int(round(float(window_start) / HOP_SEC))
        max_lag = int(round(MAX_LAG_SEC / HOP_SEC))
        mic_v = np.isfinite(mic)
        best = None
        for lag in range(-max_lag, max_lag + 1):
            # quadro i do mic ↔ quadro start+i-lag da referência (lag > 0 = mic atrasado)
            ri = start + np.arange(n) - lag
            ok = (ri >= 0) & (ri < len(ref))
            seg = np.full(n, np.nan)
            seg[ok] = ref[ri[ok]]
            ref_v = np.isfinite(seg)
            both = mic_v & ref_v
            nb = int(both.sum())
            if nb < MIN_FRAMES:
                continue
            dist = np.abs((mic[both] - seg[both] + 6.0) % 12.0 - 6.0)
            credit = np.clip((ZERO_SEMITONES - dist) / (ZERO_SEMITONES - HIT_SEMITONES), 0.0, 1.0)
            score = float(credit.mean()) * 100.0
            cov = nb / max(1, int(ref_v.sum()))
            key = (score, -abs(lag))
            if best is None or key > best[0]:
                best = (key, score, nb, cov)
        if best is None:
            return None
        _, score, nb, cov = best
        shown = max(0.0, (score - CHANCE_SCORE) / (100.0 - CHANCE_SCORE) * 100.0)
        return {"score": round(shown, 1), "raw": round(score, 1), "voiced_frames": nb, "coverage": round(cov, 3)}
    except Exception:
        logger.exception("Falha na nota de afinação do verso")
        return None
