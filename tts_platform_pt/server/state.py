"""Singletons compartilhados entre rotas HTTP.

Manter num módulo dedicado evita recarregar o modelo XTTS-v2 a cada request.
"""
from __future__ import annotations

import config
from engine.tts_engine import get_tts_engine as _get_tts_engine

VOICES_DIR = config.VOICES_DIR
CUSTOM_VOICES_DIR = config.CUSTOM_VOICES_DIR
OUTPUT_DIR = config.OUTPUT_DIR


def get_tts_engine():
    """Carrega o XTTS-v2 de forma preguiçosa, só no primeiro request de síntese."""
    return _get_tts_engine()
