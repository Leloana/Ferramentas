"""Loudness do instrumental (ITU-R BS.1770 / EBU R128) em numpy, sem ffmpeg.

O volume das músicas variava 6–10 dB de uma para outra (cada vídeo do YouTube
vem masterizado de um jeito). O `backing_track.mp3` sai da separação ajustado
para ~−16 LUFS, com um limitador simples para o pico ficar abaixo de −1 dBTP.

- K-weighting: as duas biquads da BS.1770 (prateleira de +4 dB ~1,5 kHz e
  passa-altas ~38 Hz), aplicadas no domínio da frequência (FFT do sinal inteiro;
  a gente só precisa da energia, e assim não depende de scipy).
- Gating: blocos de 400 ms com 75% de sobreposição, portão absoluto −70 LUFS e
  relativo −10 LU.
- Pico: amostra a amostra, com folga de 0,5 dB para os picos entre amostras e o
  MP3 (sem oversampling: o servidor processa minutos de áudio na CPU).
"""
from __future__ import annotations

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

TARGET_LUFS = -16.0
TRUE_PEAK_DB = -1.0
# Pico por amostra subestima o pico real (entre amostras/depois do MP3)
PEAK_MARGIN_DB = 0.5
# Não sobe mais que isso: faixa quase muda (ou erro de separação) viraria chiado
MAX_GAIN_DB = 12.0
# Diferença menor que isso não vale reescrever o áudio
MIN_CHANGE_DB = 0.5

_BLOCK_SEC = 0.4
_STEP_SEC = 0.1
_ABS_GATE = -70.0
_REL_GATE = -10.0
# janela do limitador (antecipação e soltura)
_LIMITER_SEC = 0.005


def _biquad_coeffs(kind: str, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Coeficientes (b, a) das duas etapas do K-weighting para a taxa `fs`."""
    if kind == "shelf":
        gain_db, q, fc = 4.0, 1 / math.sqrt(2), 1500.0
        a_ = 10 ** (gain_db / 40)
        w0 = 2 * math.pi * fc / fs
        alpha = math.sin(w0) / (2 * q)
        cos, sq = math.cos(w0), 2 * math.sqrt(a_) * alpha
        b = [a_ * ((a_ + 1) + (a_ - 1) * cos + sq), -2 * a_ * ((a_ - 1) + (a_ + 1) * cos),
             a_ * ((a_ + 1) + (a_ - 1) * cos - sq)]
        a = [(a_ + 1) - (a_ - 1) * cos + sq, 2 * ((a_ - 1) - (a_ + 1) * cos), (a_ + 1) - (a_ - 1) * cos - sq]
    else:  # passa-altas
        q, fc = 0.5, 38.0
        w0 = 2 * math.pi * fc / fs
        alpha = math.sin(w0) / (2 * q)
        cos = math.cos(w0)
        b = [(1 + cos) / 2, -(1 + cos), (1 + cos) / 2]
        a = [1 + alpha, -2 * cos, 1 - alpha]
    return np.array(b) / a[0], np.array(a) / a[0]


def _k_response(nfft: int, fs: float) -> np.ndarray:
    zi = np.exp(-1j * np.linspace(0, math.pi, nfft // 2 + 1))  # z^-1 nos bins da rfft
    h = np.ones_like(zi)
    for kind in ("shelf", "highpass"):
        b, a = _biquad_coeffs(kind, fs)
        h *= (b[0] + b[1] * zi + b[2] * zi * zi) / (a[0] + a[1] * zi + a[2] * zi * zi)
    return h


def _k_weight(x: np.ndarray, fs: float, chunk_sec: float = 30.0) -> np.ndarray:
    """Filtra (canais, amostras) pelo K-weighting via FFT, em pedaços de ~30 s.

    Cada pedaço leva 0,5 s do anterior (a resposta das biquads some bem antes
    disso) e sobra de zeros no fim: sem vazamento da convolução circular e sem
    alocar a FFT da música inteira.
    """
    n = x.shape[-1]
    ctx = int(fs * 0.5)
    step = int(fs * chunk_sec)
    nfft = 1 << (step + 2 * ctx - 1).bit_length()
    h = _k_response(nfft, fs)
    out = np.empty(x.shape, dtype=np.float32)
    for start in range(0, n, step):
        lo, hi = max(0, start - ctx), min(n, start + step)
        y = np.fft.irfft(np.fft.rfft(x[:, lo:hi], nfft, axis=-1) * h, nfft, axis=-1)
        out[:, start:hi] = y[:, start - lo:hi - lo]
    return out


def integrated_loudness(samples: np.ndarray, fs: float) -> float:
    """LUFS integrado de `samples` (amostras,) ou (canais, amostras), em escala ±1.

    Silêncio (nada acima do portão absoluto) devolve -inf.
    """
    x = np.atleast_2d(np.asarray(samples, dtype=np.float32))
    block, step = int(round(_BLOCK_SEC * fs)), int(round(_STEP_SEC * fs))
    if x.shape[-1] < block:
        return float("-inf")
    y = _k_weight(x, fs)
    # energia média por bloco: soma cumulativa dos quadrados
    csum = np.concatenate([np.zeros((y.shape[0], 1)), np.cumsum(np.square(y, dtype=np.float64), axis=-1)], axis=-1)
    starts = np.arange(0, y.shape[-1] - block + 1, step)
    z = (csum[:, starts + block] - csum[:, starts]) / block  # (canais, blocos)
    power = z.sum(axis=0)  # pesos G = 1 para L/R (mono igual)
    with np.errstate(divide="ignore"):
        loud = -0.691 + 10 * np.log10(power)
    gated = power[loud > _ABS_GATE]
    if gated.size == 0:
        return float("-inf")
    rel = -0.691 + 10 * np.log10(gated.mean()) + _REL_GATE
    with np.errstate(divide="ignore"):
        final = gated[-0.691 + 10 * np.log10(gated) > rel]
    return float(-0.691 + 10 * np.log10(final.mean()))


def _sliding_min(x: np.ndarray, radius: int) -> np.ndarray:
    """Mínimo em [i-radius, i+radius] (van Herk/Gil-Werman, vetorizado)."""
    w = 2 * radius + 1
    n = x.size
    padded = np.concatenate([np.full(radius, np.inf), x, np.full(radius + (-(n + 2 * radius)) % w, np.inf)])
    blocks = padded.reshape(-1, w)
    prefix = np.minimum.accumulate(blocks, axis=1).ravel()
    suffix = np.minimum.accumulate(blocks[:, ::-1], axis=1)[:, ::-1].ravel()
    idx = np.arange(n)
    return np.minimum(suffix[idx], prefix[idx + w - 1])


def limit_peaks(x: np.ndarray, ceiling: float, fs: float) -> np.ndarray:
    """Limitador com antecipação: nenhuma amostra passa de `ceiling` (escala ±1).

    O ganho necessário de cada amostra vira o mínimo numa janela de ±L e depois
    média móvel de L: a curva desce antes do pico e nunca fica acima do necessário.
    """
    x = np.atleast_2d(x)
    peak = np.abs(x).max(axis=0)
    if peak.max() <= ceiling:
        return x
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-12))
    radius = max(1, int(_LIMITER_SEC * fs))
    env = _sliding_min(need, radius)
    box = 2 * (radius // 2) + 1
    csum = np.concatenate([[0.0], np.cumsum(np.pad(env, box // 2, mode="edge"))])
    smooth = (csum[box:] - csum[:-box]) / box
    return x * np.minimum(smooth, need)[None, :]


def normalize(samples: np.ndarray, fs: float, target_lufs: float = TARGET_LUFS,
              true_peak_db: float = TRUE_PEAK_DB) -> tuple[np.ndarray, dict]:
    """Ganho para `target_lufs` + limitador. Devolve (áudio, {"lufs_before", "gain_db"}).

    Sem mudança relevante (ou silêncio) devolve o próprio áudio e gain_db 0.
    """
    x = np.atleast_2d(np.asarray(samples, dtype=np.float32))
    lufs = integrated_loudness(x, fs)
    info = {"lufs_before": None if math.isinf(lufs) else round(lufs, 2), "gain_db": 0.0}
    if math.isinf(lufs):
        return x, info
    gain_db = min(MAX_GAIN_DB, target_lufs - lufs)
    ceiling = 10 ** ((true_peak_db - PEAK_MARGIN_DB) / 20)
    over_ceiling = np.abs(x).max() * 10 ** (gain_db / 20) > ceiling
    if abs(gain_db) < MIN_CHANGE_DB and not over_ceiling:
        return x, info
    y = limit_peaks(x * np.float32(10 ** (gain_db / 20)), ceiling, fs)
    info["gain_db"] = round(gain_db, 2)
    return y, info


def normalize_audiosegment(seg):
    """Mesmo `normalize` para um pydub.AudioSegment. Devolve (AudioSegment, info)."""
    if seg.sample_width not in (2, 4):
        seg = seg.set_sample_width(2)
    full = float(1 << (8 * seg.sample_width - 1))
    dtype = np.int16 if seg.sample_width == 2 else np.int32
    raw = np.frombuffer(seg.raw_data, dtype=dtype).astype(np.float32) / full
    chans = raw.reshape(-1, seg.channels).T
    out, info = normalize(chans, seg.frame_rate)
    if info["gain_db"] == 0.0:
        return seg, info
    pcm = np.clip(np.round(out.T.ravel().astype(np.float64) * full), -full, full - 1).astype(dtype)
    return seg._spawn(pcm.tobytes()), info
