import json
from pathlib import Path

from utils.lrc import read_lrc_meta
from utils.meta import get_meta_field

def _title_fallback(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").title()


class SongManager:
    def __init__(self, songs_path: Path):
        self.songs_path = songs_path

    def list_songs(self):
        """Lista pastas de músicas que contêm meta.json ou segments.json e backing_track.mp3."""
        if not self.songs_path.exists():
            return []

        songs = []
        for item in self.songs_path.iterdir():
            if not item.is_dir():
                continue

            # Tenta carregar título e artista do meta.json
            meta_path = item / "meta.json"
            title = None
            artist = None
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        title = get_meta_field(meta, "meta", "title")
                        artist = get_meta_field(meta, "meta", "artist")
                except Exception:
                    pass

            # Fallback para lyrics.lrc ou nome da pasta
            if not title or not artist:
                lrc_title, lrc_artist = read_lrc_meta(item / "lyrics.lrc", fallback_title=_title_fallback(item.name))
                title = title or lrc_title
                artist = artist or lrc_artist

            has_segments = (item / "segments.json").exists()
            has_backing = (item / "backing_track.mp3").exists()
            is_ready = has_segments and has_backing

            songs.append({
                "id": item.name,
                "title": title,
                "artist": artist or "Artista Desconhecido",
                "is_ready": is_ready
            })

        return songs

    def get_song_data(self, song_id: str):
        """Retorna os metadados e segmentos de uma música."""
        song_dir = self.songs_path / song_id
        segments_file = song_dir / "segments.json"
        if not segments_file.exists():
            return None

        with open(segments_file, "r", encoding="utf-8") as f:
            segments = json.load(f)

        title = None
        artist = None
        meta_path = song_dir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    title = get_meta_field(meta, "meta", "title")
                    artist = get_meta_field(meta, "meta", "artist")
            except Exception:
                pass

        if not title or not artist:
            lrc_title, lrc_artist = read_lrc_meta(song_dir / "lyrics.lrc", fallback_title=_title_fallback(song_id))
            title = title or lrc_title
            artist = artist or lrc_artist

        return {"id": song_id, "title": title, "artist": artist, "segments": segments}

    def get_audio_path(self, song_id: str):
        """Retorna o caminho absoluto do backing_track.mp3."""
        path = self.songs_path / song_id / "backing_track.mp3"
        return path if path.exists() else None
