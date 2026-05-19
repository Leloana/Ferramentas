"""Helpers de I/O de áudio compartilhados entre routes e tools.

Antes existiam 2 cópias de `vocal_to_float32_mono_16k` (em `routes/upload.py`
e `tools/reinstall_song.py`) e 2 de `load_audio_full` (em `prepare_song.py`
e `generate_lrc.py`). Aqui virou fonte única — qualquer ajuste de
normalização ou resampling vale para ambos os caminhos.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from pydub import AudioSegment

from utils.whisper_params import WHISPER_SR


def vocal_to_float32_mono_16k(vocal: AudioSegment) -> np.ndarray:
    """Resamplea um `AudioSegment` para 16 kHz mono float32 normalizado."""
    resampled = vocal.set_frame_rate(WHISPER_SR).set_channels(1)
    raw = np.array(resampled.get_array_of_samples(), dtype=np.float32)
    if resampled.sample_width == 2:
        raw /= 32768.0
    elif resampled.sample_width == 4:
        raw /= 2147483648.0
    return raw


def load_audio_full(path: str | Path) -> np.ndarray:
    """Carrega arquivo de áudio inteiro como numpy float32 16kHz mono via PyAV.

    Usado pelas ferramentas CLI (`prepare_song`, `generate_lrc`) que
    trabalham com o arquivo completo em memória.
    """
    import av  # tardio: dependência pesada, só usada nas CLIs

    container = av.open(str(path))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=WHISPER_SR)

    chunks = []
    for frame in container.decode(stream):
        for resampled_frame in resampler.resample(frame):
            chunks.append(resampled_frame.to_ndarray().flatten())
    # Flush do resampler
    for resampled_frame in resampler.resample(None):
        chunks.append(resampled_frame.to_ndarray().flatten())

    return np.concatenate(chunks)
