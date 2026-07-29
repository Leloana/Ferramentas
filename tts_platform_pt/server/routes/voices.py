"""Rotas de listagem e upload de vozes (locutores embutidos do XTTS-v2 + clonagem)."""
from __future__ import annotations

import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from state import CUSTOM_VOICES_DIR, get_tts_engine

router = APIRouter(prefix="/api/voices", tags=["voices"])

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


@router.get("")
def list_voices():
    engine = get_tts_engine()
    embutidas = engine.list_builtin_speakers()
    personalizadas = sorted(p.name for p in CUSTOM_VOICES_DIR.glob("*.wav"))
    return {"embutidas": embutidas, "personalizadas": personalizadas}


@router.post("")
async def upload_voice(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .wav (6-30s de fala limpa).")

    nome_base = _SAFE_NAME_RE.sub("_", file.filename.rsplit(".", 1)[0]).strip("_") or "voz"
    destino = CUSTOM_VOICES_DIR / f"{nome_base}.wav"
    contador = 1
    while destino.exists():
        destino = CUSTOM_VOICES_DIR / f"{nome_base}_{contador}.wav"
        contador += 1

    conteudo = await file.read()
    destino.write_bytes(conteudo)

    return {"nome": destino.name}
