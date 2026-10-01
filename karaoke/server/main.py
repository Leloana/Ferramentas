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

# Limpa PATH e registra DLLs do CUDA para evitar conflitos no Windows antes de outras importações
import utils.cuda_bootstrap  # noqa: F401
import torch  # noqa: F401 (Força carregamento de DLLs do PyTorch/cuDNN primeiro)
import torchaudio  # noqa: F401


# `state` importa `utils.ffmpeg_bootstrap.bootstrap()` no nível do módulo —
# garantindo que o ffmpeg esteja no PATH **antes** de qualquer import de pydub
# que aconteça nos routers abaixo.
from state import ffmpeg_bin_dir  # noqa: F401  (lido para forçar o bootstrap)

from routes.lyrics import router as lyrics_router
from routes.queue import router as queue_router
from routes.recordings import router as recordings_router
from routes.players import router as players_router
from routes.status import router as status_router
from routes.songs import router as songs_router
from routes.upload import router as upload_router
from ws.room import router as ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"
STATIC_PREFIXES = ("/js/", "/styles/", "/assets/")
# Espera do pong do WebSocket: o Wi-Fi do Android em economia atrasa a resposta, e
# com o padrão de 20 s o celular caía com a tela apagada.
WS_PING_TIMEOUT_SEC = 60

app = FastAPI(title="Karaoke MVP Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Estáticos sem versão na URL: obriga browser e Cloudflare a revalidar (ETag)."""
    response = await call_next(request)
    if request.url.path.startswith(STATIC_PREFIXES):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/styles", StaticFiles(directory=str(CLIENT_DIR / "styles")), name="styles")
app.mount("/js", StaticFiles(directory=str(CLIENT_DIR / "js")), name="js")
app.mount("/assets", StaticFiles(directory=str(CLIENT_DIR / "assets")), name="assets")

app.include_router(songs_router)
app.include_router(lyrics_router)
app.include_router(upload_router)
app.include_router(queue_router)
app.include_router(recordings_router)
app.include_router(players_router)
app.include_router(status_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import os

    import uvicorn
    server_path = Path(__file__).resolve().parent
    ssl_key = server_path / "key.pem"
    ssl_cert = server_path / "cert.pem"

    force_http = os.environ.get("KARAOKE_HTTP", "").lower() in ("1", "true", "yes")
    # Atrás do Cloudflare Tunnel: KARAOKE_HOST=127.0.0.1 (o TLS fica no Cloudflare).
    host = os.environ.get("KARAOKE_HOST", "0.0.0.0")
    port = int(os.environ.get("KARAOKE_PORT", "8000"))

    if ssl_key.exists() and ssl_cert.exists() and not force_http:
        logger.info(f"Iniciando servidor HTTPS com SSL nos arquivos: {ssl_key} e {ssl_cert}")
        uvicorn.run(
            app,
            host=host,
            port=port,
            ssl_keyfile=str(ssl_key),
            ssl_certfile=str(ssl_cert),
            ws_ping_timeout=WS_PING_TIMEOUT_SEC,
        )
    else:
        logger.info(f"Iniciando servidor em modo HTTP padrão (sem SSL) em {host}:{port}.")
        uvicorn.run(app, host=host, port=port, ws_ping_timeout=WS_PING_TIMEOUT_SEC)
