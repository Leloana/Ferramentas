import json
from pathlib import Path

from utils.lrc import read_lrc_meta

SONGS_DIR = Path(__file__).parent / "songs"


def _title_fallback(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").title()


class SongManager:
    def __init__(self, songs_path: Path = SONGS_DIR):
        self.songs_path = songs_path

    def list_songs(self):
        """Lista pastas de músicas que contêm segments.json e backing_track.mp3."""
        if not self.songs_path.exists():
            return []

        songs = []
        for item in self.songs_path.iterdir():
            if not item.is_dir():
                continue
            if not (item / "segments.json").exists() or not (item / "backing_track.mp3").exists():
                continue

            title, artist = read_lrc_meta(item / "lyrics.lrc", fallback_title=_title_fallback(item.name))
            songs.append({"id": item.name, "title": title, "artist": artist})

        return songs

    def get_song_data(self, song_id: str):
        """Retorna os metadados e segmentos de uma música."""
        song_dir = self.songs_path / song_id
        segments_file = song_dir / "segments.json"
        if not segments_file.exists():
            return None

        with open(segments_file, "r", encoding="utf-8") as f:
            segments = json.load(f)

        title, artist = read_lrc_meta(song_dir / "lyrics.lrc", fallback_title=_title_fallback(song_id))
        return {"id": song_id, "title": title, "artist": artist, "segments": segments}

    def get_audio_path(self, song_id: str):
        """Retorna o caminho absoluto do backing_track.mp3."""
        path = self.songs_path / song_id / "backing_track.mp3"
        return path if path.exists() else None
