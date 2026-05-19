"""Parâmetros padronizados de transcrição/VAD do faster-whisper.

Centraliza a configuração usada tanto no `routes/upload.py` (transcrição
síncrona para rascunho) quanto no `tools/reinstall_song.py` (transcrição
em background para alinhamento). Antes ficava espalhado e divergente —
o que explicava a observação "baixar a primeira vez tem resultado melhor
que reinstalar".
"""
from __future__ import annotations

# Sample rate alvo do faster-whisper. O modelo é treinado em 16 kHz mono;
# qualquer áudio com outra taxa precisa ser resampled antes da transcrição.
WHISPER_SR = 16000

# VAD afrouxado: mantém o objetivo de pular intro instrumental longo
# (>700ms de silêncio) sem mesclar versos vizinhos num único segmento
# gigante (causa da colisão no align_plain_lyrics).
#
# Histórico do que mudou:
# - min_silence_duration_ms: 2000 → 700 (versos consecutivos não mesclam)
# - speech_pad_ms: 600 → 200 (menos vazamento entre frases)
# - threshold: 0.3 → 0.25 (um pouco mais sensível, ajuda em vocais limpos)
VAD_PARAMETERS = {
    "threshold": 0.25,
    "min_silence_duration_ms": 700,
    "speech_pad_ms": 200,
}

# Parâmetros base de `model.transcribe()` compartilhados.
TRANSCRIBE_KWARGS = {
    "beam_size": 5,
    "vad_filter": True,
    "vad_parameters": VAD_PARAMETERS,
    "condition_on_previous_text": False,
    "word_timestamps": True,
}
