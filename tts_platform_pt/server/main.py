"""Entrypoint do servidor da plataforma de TTS em português. Cria o FastAPI app e monta os routers."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Garante que `server/` está no sys.path para imports diretos por nome de módulo
# (ex.: `import config`) tanto via `python main.py` quanto via `uvicorn server.main:app`.
server_dir = str(Path(__file__).resolve().parent)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import config  # noqa: E402
from routes.synthesize import router as synthesize_router  # noqa: E402
from routes.voices import router as voices_router  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TTSPlatform")

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"

app = FastAPI(title="Plataforma de TTS em Português")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/styles", StaticFiles(directory=str(CLIENT_DIR / "styles")), name="styles")
app.mount("/js", StaticFiles(directory=str(CLIENT_DIR / "js")), name="js")
app.mount("/audio", StaticFiles(directory=str(config.OUTPUT_DIR)), name="audio")

app.include_router(synthesize_router)
app.include_router(voices_router)


@app.get("/")
def index():
    from fastapi.responses import FileResponse
    return FileResponse(str(CLIENT_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Iniciando servidor em http://{config.HOST}:{config.PORT}")
    uvicorn.run(app, host=config.HOST, port=config.PORT)
