"""Wrapper para importar `tools.prepare_song` sem repetir `sys.path.append` espalhado pelo código."""
from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"


def run_prepare_song(song_dir: str, language: str) -> None:
    """Executa o pipeline de alinhamento word-level do `prepare_song`."""
    tools_path = str(_TOOLS_DIR)
    if tools_path not in sys.path:
        sys.path.append(tools_path)
    from prepare_song import prepare_song  # import tardio: depende de pesos/modelos
    prepare_song(song_dir, language)
