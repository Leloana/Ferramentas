"""Download de áudio de URLs do YouTube via yt-dlp, convertido para MP3."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


async def download_youtube_audio(url: str, output_path: Path, ffmpeg_bin_dir: str | None = None) -> bool:
    """Baixa o áudio de `url` e salva como MP3 em `output_path`.

    Retorna True se o arquivo final existe e tem >1 KB. Erros de download são
    apenas logados — o sucesso é determinado pela existência do arquivo final.
    """
    import yt_dlp  # importação tardia: dependência pesada/opcional

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_template = str(output_path.with_suffix("")) + ".%(ext)s"

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "outtmpl": temp_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if ffmpeg_bin_dir:
        ydl_opts["ffmpeg_location"] = ffmpeg_bin_dir

    def _download() -> None:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    try:
        await asyncio.to_thread(_download)
    except Exception as e:
        logger.warning(f"Aviso nao-critico durante download do YouTube: {e}")

    expected_file = output_path.with_suffix(".mp3")
    if not (expected_file.exists() and expected_file.stat().st_size > 1000):
        return False

    if expected_file != output_path:
        try:
            shutil.move(str(expected_file), str(output_path))
        except Exception as move_err:
            logger.warning(f"Aviso ao mover arquivo mp3: {move_err}")

    # Limpeza proativa de arquivos residuais (.webm, .m4a, .part) causados por concorrência no Windows.
    for ext in (".webm", ".m4a", ".part"):
        leftover = output_path.with_suffix(ext)
        if leftover.exists():
            try:
                leftover.unlink()
            except Exception as unlink_err:
                logger.debug(f"Nao foi possivel remover arquivo residual {leftover}: {unlink_err}")

    return True
