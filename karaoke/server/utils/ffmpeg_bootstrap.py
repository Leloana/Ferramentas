"""Localiza o FFmpeg no Windows (instalado via Winget) e o injeta no PATH/pydub.

No Linux/macOS é no-op — assume-se que ffmpeg está no PATH do sistema.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ffmpeg_bin_dir: str | None = None


def _find_winget_ffmpeg() -> str | None:
    winget_packages_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
    if winget_packages_dir.exists():
        for p in winget_packages_dir.glob("**/bin/ffmpeg.exe"):
            return str(p.parent)

    winget_links = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links")
    if Path(winget_links).exists():
        return winget_links

    return None


def bootstrap() -> str | None:
    """Localiza ffmpeg.exe no Windows, injeta no PATH e configura o pydub.

    Retorna o diretório do binário (ou None se não-Windows / não encontrado).
    Idempotente: chame uma vez no startup.
    """
    global ffmpeg_bin_dir

    if sys.platform != "win32":
        return None

    if ffmpeg_bin_dir is not None:
        return ffmpeg_bin_dir

    found = _find_winget_ffmpeg()
    if not found:
        return None

    ffmpeg_bin_dir = found
    if found not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + found

    # Configura o pydub para apontar diretamente para os binários localizados.
    # Import tardio porque o pydub procura ffmpeg na importação.
    try:
        from pydub import AudioSegment
        ffmpeg_exe = Path(found) / "ffmpeg.exe"
        if ffmpeg_exe.exists():
            AudioSegment.converter = str(ffmpeg_exe)
            ffprobe_exe = Path(found) / "ffprobe.exe"
            if ffprobe_exe.exists():
                AudioSegment.ffprobe = str(ffprobe_exe)
    except ImportError:
        logger.debug("pydub não importado — pulando configuração de conversor")

    logger.info(f"FFmpeg localizado em: {found}")
    return found
