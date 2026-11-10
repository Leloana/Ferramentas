"""API do despertador: entrega o manifesto da edição atual e os áudios. Só lê `data/`."""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse

import config

app = FastAPI(title="Despertador", docs_url=None, redoc_url=None, openapi_url=None)
_ID = re.compile(r"^\d{4}-\d{2}-\d{2}-r\d+$")


def token() -> str:
    if not config.TOKEN_FILE.exists():
        config.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Curto o bastante para digitar no celular; rede local, revogável apagando o arquivo.
        config.TOKEN_FILE.write_text(secrets.token_hex(5), encoding="utf-8")
    return config.TOKEN_FILE.read_text(encoding="utf-8").strip()


def autenticar(authorization: str = Header(default="")) -> None:
    esperado = f"Bearer {token()}"
    if not secrets.compare_digest(authorization.encode(), esperado.encode()):
        raise HTTPException(401, "token inválido")


def _manifesto(edicao_id: str) -> tuple[dict, Path]:
    if not _ID.match(edicao_id):
        raise HTTPException(404)
    arq = config.EDICOES / edicao_id / "manifest.json"
    if not arq.exists():
        raise HTTPException(404, "edição não encontrada")
    return json.loads(arq.read_text(encoding="utf-8")), arq


def _publico(m: dict) -> dict:
    m = dict(m)
    m["assets"] = [{k: v for k, v in a.items() if k != "file"} for a in m["assets"]]
    return m


@app.get("/healthz")
def healthz():
    return {"ok": True, "tem_edicao": config.ATUAL.exists()}


@app.get("/v1/editions/latest", dependencies=[Depends(autenticar)])
def latest(request: Request, response: Response):
    if not config.ATUAL.exists():
        raise HTTPException(404, "nenhuma edição publicada")
    edicao_id = config.ATUAL.read_text(encoding="utf-8").strip()
    m, _ = _manifesto(edicao_id)
    etag = f'"{edicao_id}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return _publico(m)


@app.get("/v1/editions/{edicao_id}", dependencies=[Depends(autenticar)])
def edicao(edicao_id: str):
    return _publico(_manifesto(edicao_id)[0])


@app.get("/v1/assets/{asset_id}", dependencies=[Depends(autenticar)])
def asset(asset_id: str):
    edicao_id, _, _ = asset_id.rpartition("-")
    m, arq = _manifesto(edicao_id)
    for a in m["assets"]:
        if a["id"] == asset_id:
            return FileResponse(arq.parent / a["file"], media_type=a["mime_type"],
                                headers={"Cache-Control": "private, max-age=31536000, immutable"})
    raise HTTPException(404)
