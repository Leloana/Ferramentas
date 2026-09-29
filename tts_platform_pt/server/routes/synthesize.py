"""Rota POST /api/synthesize: pré-processa o texto (opcional) e sintetiza com XTTS-v2."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
from engine.text_preprocessor import normalize
from state import CUSTOM_VOICES_DIR, OUTPUT_DIR, get_tts_engine

logger = logging.getLogger("TTSPlatform")

router = APIRouter(prefix="/api/synthesize", tags=["synthesize"])


class SynthesizeRequest(BaseModel):
    texto: str
    voice_id: str | None = None
    language: str = config.DEFAULT_LANGUAGE
    normalizar: bool = True
    speed: float = 1.0


@router.post("")
def synthesize(req: SynthesizeRequest):
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Texto vazio.")

    aviso_normalizacao = None
    if req.normalizar:
        texto_usado, aviso_normalizacao = normalize(texto)
    else:
        texto_usado = texto

    speaker = None
    speaker_wav = None
    if req.voice_id and req.voice_id.startswith("custom:"):
        nome_arquivo = req.voice_id.split(":", 1)[1]
        caminho = CUSTOM_VOICES_DIR / nome_arquivo
        if not caminho.exists():
            raise HTTPException(status_code=404, detail=f"Voz personalizada '{nome_arquivo}' não encontrada.")
        speaker_wav = caminho
    else:
        speaker = req.voice_id
        if speaker:
            # Voz embutida que não existe explodia lá dentro do XTTS como 500 sem
            # explicação (aconteceu com "Tais Galante", que nunca existiu e estava
            # em 22 arquivos vozes.md). Aqui vira 400 dizendo o que foi pedido.
            disponiveis = get_tts_engine().list_builtin_speakers()
            if speaker not in disponiveis:
                parecidas = [v for v in disponiveis if v.split()[0].lower() == speaker.split()[0].lower()]
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Voz embutida '{speaker}' não existe. "
                        + (f"Parecidas: {', '.join(parecidas)}. " if parecidas else "")
                        + "Veja a lista completa em GET /api/voices."
                    ),
                )

    output_path = OUTPUT_DIR / f"{uuid.uuid4().hex}.wav"

    try:
        engine = get_tts_engine()
        _, frases = engine.synthesize(
            text=texto_usado,
            output_path=output_path,
            language=req.language,
            speaker=speaker,
            speaker_wav=speaker_wav,
            speed=req.speed,
        )
    except Exception as e:
        logger.error(f"Falha ao sintetizar áudio: {e}")
        raise HTTPException(status_code=500, detail="Falha ao gerar áudio.") from e

    return {
        "audio_url": f"/audio/{output_path.name}",
        "texto_usado": texto_usado,
        "aviso_normalizacao": aviso_normalizacao,
        "frases": frases,
    }
