"""Download de áudio de URLs do YouTube via yt-dlp, convertido para MP3."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_RETRY_DELAY_SEC = 5.0


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

    expected_file = output_path.with_suffix(".mp3")
    # O YouTube às vezes recusa um pedido no meio de vários seguidos (playlist):
    # a mesma URL baixa normal logo depois. Tenta de novo antes de dar erro.
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            await asyncio.to_thread(_download)
        except Exception as e:
            logger.warning(f"Aviso nao-critico durante download do YouTube (tentativa {attempt}): {e}")
        if expected_file.exists() and expected_file.stat().st_size > 1000:
            break
        if attempt < DOWNLOAD_ATTEMPTS:
            await asyncio.sleep(DOWNLOAD_RETRY_DELAY_SEC * attempt)
    else:
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


async def get_youtube_video_info(url: str) -> dict:
    """Extrai rapidamente metadados do vídeo do YouTube sem fazer o download."""
    import yt_dlp

    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }

    def _extract() -> dict:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_extract)
        return split_artist_title(info.get("title", ""))
    except Exception as e:
        logger.error(f"Erro ao extrair info do YouTube: {e}", exc_info=True)
        return {"artist": "", "title": ""}


_TITLE_SEPARATORS = [" - ", " – ", " — ", " | ", " ~ ", " : "]
# Ex: "Teenagers (Official Music Video)" -> "Teenagers"
_VIDEO_TAG_RE = r"\s*[\(\[][^)]*?(official|oficial|video|vídeo|clip|clipe|audio|áudio|lyric|karaoke|instrumental|legendado|cover|lyrics|4k|hd|subtitles|traducao|tradução|ao vivo|live)[^)]*?[\)\]]"


# Nome do canal → nome do artista: "Official Arctic Monkeys", "Oasis - Topic", "AdeleVEVO".
# Com o nome do canal a busca da letra (LRCLIB) falhava ou vinha sem sincronia.
_CHANNEL_PREFIX_RE = r"^\s*(official|oficial)\s+"
_CHANNEL_SUFFIX_RE = r"\s*(-\s*topic|vevo|official|oficial|official channel|canal oficial)\s*$"


def _clean_channel(channel: str) -> str:
    import re

    name = channel or ""
    for _ in range(2):  # "Official Artist Official Channel"
        name = re.sub(_CHANNEL_PREFIX_RE, "", name, flags=re.IGNORECASE)
        name = re.sub(_CHANNEL_SUFFIX_RE, "", name, flags=re.IGNORECASE)
    return name.strip() or (channel or "").strip()


def split_artist_title(raw_title: str, fallback_artist: str = "") -> dict:
    """Separa "Artista - Título" e limpa tags de vídeo; sem separador, usa o canal."""
    import re

    artist = ""
    title = raw_title or ""
    for sep in _TITLE_SEPARATORS:
        if sep in title:
            artist, title = (part.strip() for part in title.split(sep, 1))
            break
    if not artist and fallback_artist:
        artist = _clean_channel(fallback_artist)

    title = re.sub(_VIDEO_TAG_RE, "", title, flags=re.IGNORECASE).strip().strip("\"'")
    artist = re.sub(_VIDEO_TAG_RE, "", artist, flags=re.IGNORECASE).strip().strip("\"'")
    return {"artist": artist, "title": title}


async def search_youtube(query: str, limit: int = 8) -> list[dict]:
    """Busca vídeos no YouTube pelo nome (sem baixar). Rápido: só a listagem."""
    import yt_dlp

    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }

    def _search() -> dict:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    info = await asyncio.to_thread(_search)
    results = []
    for entry in (info or {}).get("entries") or []:
        item = _entry_to_result(entry)
        if item:
            results.append(item)
    return results


# Mix automático do YouTube (list=RD...) não tem fim: corta aqui
PLAYLIST_LIMIT = 50
# vídeos que a playlist ainda lista mas não dá para baixar
_UNAVAILABLE_TITLES = {"[private video]", "[deleted video]", "[vídeo privado]", "[vídeo excluído]"}


def is_playlist_url(url: str) -> bool:
    """Link de playlist do YouTube / YouTube Music (tem `list=`)."""
    import re

    return bool(re.search(r"(youtube\.com|youtu\.be)/.*[?&]list=[\w-]+", url or "", re.IGNORECASE))


def _entry_to_result(entry: dict) -> dict | None:
    """Item da listagem (busca ou playlist) no formato do front; None se não for um vídeo baixável."""
    video_id = entry.get("id")
    if not video_id or entry.get("ie_key") not in (None, "Youtube"):
        return None
    if (entry.get("title") or "").strip().lower() in _UNAVAILABLE_TITLES:
        return None
    channel = entry.get("channel") or entry.get("uploader") or ""
    guess = split_artist_title(entry.get("title") or "", fallback_artist=channel)
    return {
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": entry.get("title") or "",
        "channel": channel,
        "duration": entry.get("duration"),
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        "artist_guess": guess["artist"],
        "title_guess": guess["title"],
    }


# "1. Música", "01 - Música", "1) Música": número da faixa no começo do título
_TRACK_NUMBER_RE = r"^\s*\d{1,2}\s*[.)\-]\s*"
# sobras comuns no fim de uploads de fã: "+lyrics", "(lyrics)" já sai em _VIDEO_TAG_RE
_TRAILING_JUNK_RE = r"\s*\+\s*(lyrics|letra|legendado)\s*$"


def _fix_playlist_guesses(results: list[dict]) -> None:
    """Acerta artista/título olhando a playlist inteira (álbum).

    Uploads de fã vêm como "1. Música - Artista - Álbum +lyrics": o palpite
    de vídeo a vídeo tomava a música pelo artista. Numa playlist, a parte que
    se repete na maioria dos títulos é o artista (ou o álbum); o título é a
    primeira parte que muda de vídeo para vídeo."""
    import re
    from collections import Counter

    if len(results) < 2:
        return
    split = []
    for item in results:
        raw = re.sub(_VIDEO_TAG_RE, "", item["title"], flags=re.IGNORECASE)
        raw = re.sub(_TRAILING_JUNK_RE, "", raw, flags=re.IGNORECASE)
        split.append([part.strip() for part in raw.split(" - ") if part.strip()])

    needed = len(results) * 0.6
    constant: dict[int, str] = {}  # posição -> valor que se repete
    for pos in range(max(len(parts) for parts in split)):
        values = Counter(parts[pos].lower() for parts in split if len(parts) > pos)
        if values:
            value, count = values.most_common(1)[0]
            if count >= needed:
                constant[pos] = value
    if not constant:
        return
    artist_pos = min(constant)  # artista antes do álbum ("Música - Artista - Álbum")
    for item, parts in zip(results, split):
        if len(parts) <= artist_pos or parts[artist_pos].lower() != constant[artist_pos]:
            continue  # foge do padrão (faixa bônus, outro artista): fica o palpite do vídeo
        title = next((part for pos, part in enumerate(parts) if pos not in constant), "")
        title = re.sub(_TRACK_NUMBER_RE, "", title).strip().strip("\"'")
        if title:
            item["artist_guess"] = parts[artist_pos]
            item["title_guess"] = title


async def list_youtube_playlist(url: str, limit: int = PLAYLIST_LIMIT) -> dict:
    """Vídeos de uma playlist (sem baixar): {"title", "results", "truncated"}."""
    import yt_dlp

    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        # um a mais só para saber se a playlist foi cortada
        "playlistend": limit + 1,
    }

    def _extract() -> dict:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await asyncio.to_thread(_extract) or {}
    results: list[dict] = []
    seen: set[str] = set()
    entries = list(info.get("entries") or [])
    for entry in entries[:limit]:
        item = _entry_to_result(entry or {})
        if item and item["id"] not in seen:
            seen.add(item["id"])
            results.append(item)
    _fix_playlist_guesses(results)
    return {"title": info.get("title") or "", "results": results, "truncated": len(entries) > limit}
