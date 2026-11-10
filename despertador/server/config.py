"""Configuração do servidor do despertador. Segredos só no .env (gitignored)."""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"               # tudo que é gerado (gitignored)
EDICOES = DATA / "edicoes"         # uma pasta imutável por edição
CACHE_TTS = DATA / "cache_tts"     # MP3 reaproveitado por hash do texto+voz+modelo
GASTOS = DATA / "gastos.jsonl"     # caracteres enviados à ElevenLabs (um por linha)
TOKEN_FILE = DATA / "token.txt"    # token do aparelho
ATUAL = DATA / "atual.txt"         # ponteiro para a edição mais recente
ENV_FILE = BASE / ".env"

FUSO = "America/Sao_Paulo"
PORTA = int(os.environ.get("DESPERTADOR_PORTA", "8040"))
VALIDADE_HORAS = 36                # depois disso o app trata o jornal como vencido

ELEVEN_MODEL = "eleven_v4_turbo"
ELEVEN_VOZ = "7i7dgyCkKt4c16dLtwT3"  # David (a mesma dos vídeos)
ELEVEN_AJUSTES = {"stability": 0.5, "similarity_boost": 0.75, "style": 0.2}
TETO_TOTAL_CREDITOS = 10_000       # créditos separados para o despertador
TETO_POR_EDICAO = 2_500            # caracteres por chamada
# Estimativa para checar o teto ANTES de chamar; o gasto real vem do cabeçalho
# `character-cost` da resposta (turbo v4 medido em 10/11/2026: 0,25 crédito/caractere).
CREDITOS_POR_CARACTERE = 0.25


def env(nome: str) -> str | None:
    if os.environ.get(nome):
        return os.environ[nome]
    if ENV_FILE.exists():
        for linha in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            k, _, v = linha.partition("=")
            if k.strip() == nome:
                return v.strip().strip('"') or None
    return None
