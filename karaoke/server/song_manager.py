import os
import json
from pathlib import Path

SONGS_DIR = Path(__file__).parent / "songs"

class SongManager:
    def __init__(self, songs_path: Path = SONGS_DIR):
        self.songs_path = songs_path

    def list_songs(self):
        """Lista pastas de músicas que contêm segments.json e backing_track.mp3."""
        songs = []
        if not self.songs_path.exists():
            return []
            
        for item in self.songs_path.iterdir():
            if item.is_dir():
                segments_file = item / "segments.json"
                audio_file = item / "backing_track.mp3"
                if segments_file.exists() and audio_file.exists():
                    # Fallback com base no nome do diretório
                    title = item.name.replace("_", " ").replace("-", " ").title()
                    artist = ""
                    
                    # Tenta extrair metadados reais do lyrics.lrc
                    lrc_file = item / "lyrics.lrc"
                    if lrc_file.exists():
                        try:
                            with open(lrc_file, "r", encoding="utf-8") as f:
                                for line in f:
                                    line_clean = line.strip()
                                    if line_clean.startswith("[ti:"):
                                        title = line_clean.split(":", 1)[1].rstrip("]").strip()
                                    elif line_clean.startswith("[ar:"):
                                        artist = line_clean.split(":", 1)[1].rstrip("]").strip()
                                    
                                    # Se começou a marcação de tempos tradicional, pare a leitura
                                    if line_clean.startswith("[0") or line_clean.startswith("[1") or line_clean.startswith("[2"):
                                        break
                        except Exception:
                            pass
                            
                    songs.append({
                        "id": item.name,
                        "title": title,
                        "artist": artist
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
            
        # Fallback com base no nome do diretório
        title = song_id.replace("_", " ").replace("-", " ").title()
        artist = ""
        
        # Tenta extrair metadados reais do lyrics.lrc
        lrc_file = song_dir / "lyrics.lrc"
        if lrc_file.exists():
            try:
                with open(lrc_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line_clean = line.strip()
                        if line_clean.startswith("[ti:"):
                            title = line_clean.split(":", 1)[1].rstrip("]").strip()
                        elif line_clean.startswith("[ar:"):
                            artist = line_clean.split(":", 1)[1].rstrip("]").strip()
                        if line_clean.startswith("[0") or line_clean.startswith("[1") or line_clean.startswith("[2"):
                            break
            except Exception:
                pass
            
        return {
            "id": song_id,
            "title": title,
            "artist": artist,
            "segments": segments
        }

    def get_audio_path(self, song_id: str):
        """Retorna o caminho absoluto do backing_track.mp3."""
        path = self.songs_path / song_id / "backing_track.mp3"
        return path if path.exists() else None
