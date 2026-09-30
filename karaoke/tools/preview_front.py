"""Pré-visualização do front sem GPU, sem FastAPI e sem dependências.

Serve `client/` montando os parciais do index.html do mesmo jeito que o servidor
(server/utils/html_includes.py) e responde a API com dados de exemplo: lista as
músicas de server/songs/*/meta.json e devolve uma fila fictícia. Não há WebSocket
nem áudio, então a partida não roda — serve para ver telas, abas, modais e a
navegação por controle remoto.

    python tools/preview_front.py            # http://localhost:8765
    python tools/preview_front.py --port 9000

Telas úteis: `/?tv=1` (modo TV), `/?role=mic&room=1234` (celular-microfone).
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = ROOT / "client"
SONGS_DIR = ROOT / "server" / "songs"
STATIC_PREFIXES = ("/js/", "/styles/", "/assets/")

sys.path.insert(0, str(ROOT / "server"))
from utils.html_includes import render_page  # noqa: E402  (módulo puro, sem FastAPI)
import players  # noqa: E402  (perfis: só biblioteca padrão)


def seed_sample_players() -> None:
    """Perfis de exemplo numa pasta temporária (não toca nos perfis reais)."""
    import tempfile

    players.PLAYERS_DIR = Path(tempfile.mkdtemp(prefix="preview-players-"))
    games = [
        ("Marcelo", "ze-assassino-compulsivo-o-terno", "Zé Assassino Compulsivo - O Terno", 94.2, 71.0),
        ("Marcelo", "geni-e-o-zepelim-chico-buarque", "Geni e o Zepelim - Chico Buarque", 83.1, 64.0),
        ("Marcelo", "ze-assassino-compulsivo-o-terno", "Zé Assassino Compulsivo - O Terno", 88.0, 69.0),
        ("Ana", "geni-e-o-zepelim-chico-buarque", "Geni e o Zepelim - Chico Buarque", 90.4, 80.0),
        ("Ana", "a-wolf-at-the-door-radiohead", "A Wolf at the Door - Radiohead", 76.5, 58.0),
        ("Beto", "a-wolf-at-the-door-radiohead", "A Wolf at the Door - Radiohead", 62.0, None),
    ]
    for name, song_id, title, score, pitch in games:
        players.record_game(name, song_id, title, score, pitch=pitch)

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")

SAMPLE_QUEUE = [
    {"id": "q1", "title": "Música de exemplo", "status": "separating", "progress_pct": 45,
     "has_lrc": True, "added_by": "Celular"},
    {"id": "q2", "title": "Outra música", "status": "queued", "progress_pct": 0, "has_plain_lyrics": True},
]


def list_songs() -> list[dict]:
    songs = []
    for item in sorted(SONGS_DIR.iterdir()) if SONGS_DIR.exists() else []:
        if not item.is_dir():
            continue
        title, artist = item.name.replace("-", " ").title(), "Artista Desconhecido"
        meta_path = item / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8")).get("meta", {})
                title = meta.get("title") or title
                artist = meta.get("artist") or artist
            except (ValueError, OSError):
                pass
        songs.append({"id": item.name, "title": title, "artist": artist, "is_ready": True})
    if songs:
        songs[-1]["is_ready"] = False  # mostra também o card "Pendente"
    return songs


def youtube_search(query: str) -> list[dict]:
    """Busca real se o yt-dlp estiver instalado; senão, resultados fictícios."""
    try:
        import asyncio
        from utils.youtube import search_youtube
        return asyncio.run(search_youtube(query, limit=8))
    except ImportError:
        return [{"id": f"demo{i}", "url": f"https://www.youtube.com/watch?v=demo{i}",
                 "title": f"{query} (exemplo {i})", "channel": "Canal de exemplo", "duration": 200 + i,
                 "thumbnail": "", "artist_guess": "Artista", "title_guess": query} for i in range(1, 4)]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silencioso
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        self._send(json.dumps(data).encode("utf-8"), "application/json", status)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(render_page(CLIENT_DIR).encode("utf-8"), "text/html; charset=utf-8")
        if path.startswith(STATIC_PREFIXES):
            file = (CLIENT_DIR / path.lstrip("/")).resolve()
            if CLIENT_DIR.resolve() in file.parents and file.is_file():
                ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                return self._send(file.read_bytes(), ctype)
            return self._send(b"not found", "text/plain", 404)
        if path.startswith("/api/songs/") and path.endswith("/cover"):
            from utils.cover import find_cover
            song_dir = (SONGS_DIR / path.split("/")[3]).resolve()
            cover = find_cover(song_dir) if SONGS_DIR.resolve() in song_dir.parents else None
            if cover:
                return self._send(cover.read_bytes(), "image/jpeg")
            return self._json({"detail": "Sem capa"}, 404)
        if path in ("/api/songs", "/songs"):
            return self._json(list_songs())
        if path == "/api/queue/status":
            return self._json({"queue": SAMPLE_QUEUE, "gpu_busy": False})
        if path == "/api/get-ip":
            return self._json({"ip": "127.0.0.1"})
        if path == "/api/public-url":
            return self._json({"url": None})
        if path == "/api/youtube-search":
            query = (parse_qs(urlparse(self.path).query).get("q") or [""])[0]
            return self._json({"results": youtube_search(query)})
        if path == "/api/fetch-lyrics":
            return self._json({"success": False})
        if path == "/api/status":
            return self._json({
                "gpu": {"locked": False, "game_active": False, "whisper_model": "large-v3-turbo (preview)"},
                "queue": {"total": len(SAMPLE_QUEUE), "by_status": {"separating": 1, "queued": 1}},
                "rooms": [{"id": "1234", "song": "Geni e o Zepelim - Chico Buarque", "display": True,
                           "players": ["Ana", "Marcelo"], "waiting_mics": 0, "singing": True, "pending_verses": 1,
                           "verse_latency_median": 1.4, "verse_latency_p90": 2.2, "verses_measured": 18}],
                "disk": {"free_gb": 212.4, "total_gb": 476.9},
                "songs": len(list_songs()),
            })
        if path == "/api/players":
            return self._json({"players": players.list_profiles()})
        if path.startswith("/api/players/"):
            from urllib.parse import unquote
            profile = players.load_profile(unquote(path.split("/", 3)[3]))
            if not profile:
                return self._json({"detail": "Cantor sem partidas"}, 404)
            return self._json(players.profile_detail(profile))
        return self._json({"detail": "preview: rota não simulada"}, 404)

    def do_POST(self):
        self._json({"success": False, "detail": "preview: somente leitura"}, 400)

    do_DELETE = do_POST


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    seed_sample_players()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Preview do front em http://{args.host}:{args.port}  (Ctrl+C para sair)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
