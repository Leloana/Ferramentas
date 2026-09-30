"""Deixa um valor pronto para JSON (envio por WebSocket e gravação da partida).

Números do numpy viram int/float do Python, arrays viram listas e o que não tiver
tradução vira texto. Uma mensagem de fim de jogo que não serializa não chegava a
ninguém: a TV e o celular ficavam presos na tela da partida.
"""
from __future__ import annotations

import math

import numpy as np


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [jsonable(v) for v in value.tolist()]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        return f if math.isfinite(f) else None
    if value is None or isinstance(value, str):
        return value
    return str(value)
