import json
import logging

import ollama

import config

logger = logging.getLogger("TTSPlatform")


def normalize(text: str, model: str = config.OLLAMA_MODEL) -> str:
    """Normaliza o texto para leitura em voz alta via Ollama.

    Em qualquer falha (Ollama fora do ar, resposta inválida), retorna o texto
    original sem quebrar a síntese — a normalização é sempre opcional.
    """
    prompt = f"""
Reescreva o texto abaixo para ser lido em voz alta por um sintetizador de fala,
em português do Brasil. Regras:
- Expanda siglas e abreviações (ex: "Dr." -> "Doutor", "Av." -> "Avenida").
- Escreva números por extenso quando fizer sentido para a fala.
- Ajuste a pontuação para criar pausas naturais.
- NÃO mude o significado do texto nem adicione informação nova.

TEXTO:
{text}

Responda APENAS um JSON no formato:
{{"texto_normalizado": "..."}}
"""
    try:
        response = ollama.generate(model=model, prompt=prompt, format="json")
        data = json.loads(response["response"])
        normalizado = (data.get("texto_normalizado") or "").strip()
        return normalizado or text
    except Exception as e:
        logger.warning(f"Falha ao normalizar texto via Ollama, usando texto original: {e}")
        return text
