"""Stand-in mínimo do essentia (sem build pra Windows) só para o Pop2Piano do transformers.

O transformers usa apenas `essentia.standard.RhythmExtractor2013` para achar as batidas.
Aqui ele devolve as batidas que o nosso pipeline já calculou (ou librosa, se não houver).
"""
__version__ = "0.0-stub"
from . import standard  # noqa: F401
