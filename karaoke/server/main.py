"""Entrypoint do servidor de karaokê. Cria o FastAPI app e monta os routers."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Garante que `server/` está no sys.path para imports diretos por nome de módulo
# (ex.: `from state import ...`) tanto via `python main.py` quanto via `uvicorn server.main:app`.
server_dir = str(Path(__file__).resolve().parent)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# `state` importa `utils.ffmpeg_bootstrap.bootstrap()` no nível do módulo —
# garantindo que o ffmpeg esteja no PATH **antes** de qualquer import de pydub
# que aconteça nos routers abaixo.
from state import ffmpeg_bin_dir  # noqa: F401  (lido para forçar o bootstrap)

from routes.lyrics import router as lyrics_router
from routes.songs import router as songs_router
from routes.upload import router as upload_router
from ws.room import router as ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"

app = FastAPI(title="Karaoke MVP Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/styles", StaticFiles(directory=str(CLIENT_DIR / "styles")), name="styles")
app.mount("/js", StaticFiles(directory=str(CLIENT_DIR / "js")), name="js")

app.include_router(songs_router)
app.include_router(lyrics_router)
app.include_router(upload_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn
    # Em produção, carregar caminhos de cert.pem e key.pem
    uvicorn.run(app, host="0.0.0.0", port=8000)
