"""Síntese via API da ElevenLabs, com o mesmo retorno de `TTSEngine.synthesize`.

Usa o endpoint `/with-timestamps`, que devolve o tempo de cada caractere do
texto enviado — dá pra montar `frases`/`palavras` direto disso, sem passar
pelo alinhador forçado (MMS_FA) nem sintetizar frase por frase.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
import wave
from pathlib import Path

import requests

import config

logger = logging.getLogger("TTSPlatform")

_API = "https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps"
_SAMPLE_RATE = 44100

# Fim de frase: pontuação final seguida de espaço/quebra de linha.
_FIM_FRASE_RE = re.compile(r"(?<=[.!?…])[\"”')\]]*\s+")
# Mesma tokenização de `tts_engine._limpar_pontuacao(frase).split()`: trocar
# `[^\w\s-]` por espaço e quebrar em espaço deixa exatamente as sequências de
# `[\w-]` — as palavras precisam bater 1:1 com o que `montar_video.py` agrupa.
_PALAVRA_RE = re.compile(r"[\w-]+", re.UNICODE)


class ElevenError(RuntimeError):
    pass


def _chave() -> str:
    chave = os.environ.get("ELEVENLABS_API_KEY")
    if not chave and config.ENV_FILE.exists():
        for linha in config.ENV_FILE.read_text(encoding="utf-8").splitlines():
            k, _, v = linha.partition("=")
            if k.strip() == "ELEVENLABS_API_KEY":
                chave = v.strip().strip('"')
    if not chave:
        raise ElevenError(f"Falta ELEVENLABS_API_KEY em {config.ENV_FILE} ou no ambiente.")
    return chave


def _frases(texto: str) -> list[tuple[int, int]]:
    """(início, fim) de cada frase dentro de `texto`, sem os espaços das bordas."""
    spans, inicio = [], 0
    for m in _FIM_FRASE_RE.finditer(texto):
        spans.append((inicio, m.start()))
        inicio = m.end()
    spans.append((inicio, len(texto.rstrip())))
    return [(a, b) for a, b in spans if texto[a:b].strip()]


def _blocos(texto: str, frases: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Agrupa frases inteiras em blocos de até `ELEVEN_MAX_CHARS` caracteres."""
    blocos = []
    for a, b in frases:
        if blocos and b - blocos[-1][0] <= config.ELEVEN_MAX_CHARS:
            blocos[-1] = (blocos[-1][0], b)
        else:
            blocos.append((a, b))
    return blocos


def _mp3_para_pcm(mp3: bytes) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "-", "-ar", str(_SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-"],
        input=mp3, capture_output=True, check=True,
    ).stdout


def _sintetizar_bloco(texto: str, voz: str, language: str, speed: float, anterior: str, seguinte: str):
    ajustes = dict(config.ELEVEN_AJUSTES)
    if speed != 1.0:
        ajustes["speed"] = min(max(speed, config.ELEVEN_SPEED_MIN), config.ELEVEN_SPEED_MAX)
    corpo = {"text": texto, "model_id": config.ELEVEN_MODEL, "language_code": language[:2], "voice_settings": ajustes}
    # Contexto dos blocos vizinhos mantém a entonação contínua entre chamadas
    # (o v3/v4 não aceita esses campos; só são mandados quando existem).
    if anterior:
        corpo["previous_text"] = anterior
    if seguinte:
        corpo["next_text"] = seguinte
    r = requests.post(
        _API.format(voz=voz), params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": _chave()}, json=corpo, timeout=300,
    )
    if r.status_code == 400 and (anterior or seguinte) and ("previous_text" in r.text or "next_text" in r.text):
        return _sintetizar_bloco(texto, voz, language, speed, "", "")
    if not r.ok:
        raise ElevenError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    dados = r.json()
    al = dados["alignment"]
    if len(al["characters"]) != len(texto):
        raise ElevenError("Alinhamento da ElevenLabs não bate com o texto enviado.")
    return _mp3_para_pcm(base64.b64decode(dados["audio_base64"])), al["character_start_times_seconds"], al["character_end_times_seconds"]


def synthesize(text: str, output_path: Path, voice_id: str, language: str = config.DEFAULT_LANGUAGE, speed: float = 1.0):
    """Sintetiza `text` com a voz `voice_id` da ElevenLabs. Retorna `(output_path, frases)`
    no mesmo formato de `TTSEngine.synthesize` (tempos em segundos no áudio final)."""
    frases = _frases(text)
    blocos = _blocos(text, frases)

    # Tempo de início/fim de cada caractere do texto inteiro, já somando o
    # deslocamento dos blocos anteriores.
    inicio_c = [0.0] * len(text)
    fim_c = [0.0] * len(text)
    pcm = bytearray()
    for i, (a, b) in enumerate(blocos):
        anterior = text[blocos[i - 1][0]:blocos[i - 1][1]][-500:] if i else ""
        seguinte = text[blocos[i + 1][0]:blocos[i + 1][1]][:500] if i + 1 < len(blocos) else ""
        audio, ini, fim = _sintetizar_bloco(text[a:b], voice_id, language, speed, anterior, seguinte)
        deslocamento = len(pcm) / 2 / _SAMPLE_RATE
        for k in range(b - a):
            inicio_c[a + k] = ini[k] + deslocamento
            fim_c[a + k] = fim[k] + deslocamento
        pcm += audio
    logger.info(f"ElevenLabs: {len(text)} caracteres em {len(blocos)} chamada(s), voz {voice_id}")

    with wave.open(str(output_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(bytes(pcm))

    # O alinhamento às vezes passa uns centésimos do fim do áudio decodificado.
    duracao = len(pcm) / 2 / _SAMPLE_RATE
    inicio_c = [min(t, duracao) for t in inicio_c]
    fim_c = [min(t, duracao) for t in fim_c]

    timings = []
    for a, b in frases:
        palavras = [
            {"texto": m.group(), "inicio_s": round(inicio_c[a + m.start()], 3), "fim_s": round(fim_c[a + m.end() - 1], 3)}
            for m in _PALAVRA_RE.finditer(text[a:b])
        ]
        timings.append({
            "texto": text[a:b],
            "inicio_s": round(inicio_c[a], 3),
            "fim_s": round(fim_c[b - 1], 3),
            "palavras": palavras,
        })
    return output_path, timings
