"""Adaptador ElevenLabs com cache por hash e teto de gasto em créditos (custo real do cabeçalho character-cost)."""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import config


class VozErro(RuntimeError):
    pass


def gasto_total() -> int:
    """Créditos ElevenLabs gastos pelo despertador (real, ou estimado quando faltou o cabeçalho)."""
    if not config.GASTOS.exists():
        return 0
    return sum(json.loads(l)["creditos"] for l in config.GASTOS.read_text(encoding="utf-8").splitlines() if l.strip())


def _estimar(caracteres: int) -> int:
    return math.ceil(caracteres * config.CREDITOS_POR_CARACTERE)


def _registrar(caracteres: int, creditos: int, real: bool, motivo: str, chave_cache: str) -> None:
    config.GASTOS.parent.mkdir(parents=True, exist_ok=True)
    with config.GASTOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "caracteres": caracteres, "creditos": creditos, "creditos_reais": real,
            "modelo": config.ELEVEN_MODEL,
            "voz": config.ELEVEN_VOZ, "motivo": motivo, "cache": chave_cache,
        }, ensure_ascii=False) + "\n")


def sintetizar(texto: str, destino: Path, motivo: str, teto: int = config.TETO_POR_EDICAO) -> bool:
    """Gera MP3 em `destino`. Devolve True se chamou a API, False se veio do cache."""
    texto = " ".join(texto.split()) if "\n" not in texto else "\n".join(" ".join(p.split()) for p in texto.split("\n"))
    params = {"t": texto, "m": config.ELEVEN_MODEL, "v": config.ELEVEN_VOZ, "a": config.ELEVEN_AJUSTES}
    chave_cache = hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    cache = config.CACHE_TTS / f"{chave_cache}.mp3"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        destino.write_bytes(cache.read_bytes())
        return False

    n = len(texto)
    if n > teto:
        raise VozErro(f"Texto com {n} caracteres passa do teto por edição ({teto}).")
    usado, previsto = gasto_total(), _estimar(n)
    if usado + previsto > config.TETO_TOTAL_CREDITOS:
        raise VozErro(f"Orçamento esgotado: {usado} créditos usados + ~{previsto} > {config.TETO_TOTAL_CREDITOS}.")
    chave = config.env("ELEVENLABS_API_KEY")
    if not chave:
        raise VozErro(f"Falta ELEVENLABS_API_KEY em {config.ENV_FILE}.")

    corpo = json.dumps({"text": texto, "model_id": config.ELEVEN_MODEL, "language_code": "pt",
                        "voice_settings": config.ELEVEN_AJUSTES}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVEN_VOZ}?output_format=mp3_44100_128",
        data=corpo, method="POST",
        headers={"xi-api-key": chave, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            audio = r.read()
            custo = r.headers.get("character-cost")
    except urllib.error.HTTPError as e:
        raise VozErro(f"ElevenLabs {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        # Sem resposta: pode ter cobrado ou não. Registra para não estourar o teto por engano.
        _registrar(n, previsto, False, motivo + " (falha de rede, consumo incerto)", chave_cache)
        raise VozErro(f"Falha de rede na ElevenLabs: {e}") from None
    if len(audio) < 2000:
        raise VozErro("ElevenLabs devolveu áudio vazio ou curto demais.")
    real = custo is not None and custo.isdigit()
    _registrar(n, int(custo) if real else previsto, real, motivo, chave_cache)
    config.CACHE_TTS.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(audio)
    tmp.replace(cache)
    destino.write_bytes(audio)
    time.sleep(0.2)
    return True
