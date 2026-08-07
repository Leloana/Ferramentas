import json
import logging
import shutil
import subprocess

import ollama
import torch

import config

logger = logging.getLogger("TTSPlatform")


def _free_vram_mb():
    """VRAM livre agora, em MB, via `nvidia-smi`; None se não for possível medir.

    Usa `nvidia-smi` (NVML) em vez de `torch.cuda.mem_get_info()`: no Windows
    com driver WDDM, o `mem_get_info()` do PyTorch não enxerga corretamente a
    VRAM reservada por OUTROS processos (ex.: o Ollama, que roda separado) —
    chegou a reportar 11GB livres quando só havia 4GB de verdade. O
    `nvidia-smi` reflete o uso físico real entre todos os processos.
    """
    if not shutil.which("nvidia-smi"):
        return None
    try:
        saida = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return float(saida.stdout.strip().splitlines()[0])
    except Exception as e:
        logger.warning(f"Falha ao consultar VRAM livre via nvidia-smi: {e}")
        return None


def pick_num_ctx():
    """Escolhe o maior patamar de num_ctx que cabe na VRAM livre, reservando
    espaço pro XTTS-v2. Retorna None se não sobrar nem o mínimo (ou se não foi
    possível medir a VRAM com confiança) — nesse caso o Ollama não deve ser
    chamado, para não arriscar um OOM na GPU."""
    if not torch.cuda.is_available():
        # Sem GPU não há disputa de VRAM entre Ollama e XTTS-v2 (cada um usa
        # RAM/CPU do seu jeito); contexto fixo é suficiente.
        return config.OLLAMA_NUM_CTX_CPU_FALLBACK

    free_mb = _free_vram_mb()
    if free_mb is None:
        # Há GPU mas não deu pra medir com confiança: mais seguro pular o
        # Ollama do que arriscar um OOM baseado numa suposição.
        return None

    orcamento_mb = free_mb - config.OLLAMA_XTTS_RESERVE_MB
    if orcamento_mb < config.OLLAMA_MIN_FREE_MB:
        return None

    for num_ctx, custo_mb in config.OLLAMA_NUM_CTX_TIERS_MB:
        if custo_mb <= orcamento_mb:
            return num_ctx
    return None


def normalize(text: str, model: str = config.OLLAMA_MODEL) -> tuple[str, str | None]:
    """Normaliza o texto para leitura em voz alta via Ollama.

    Retorna (texto_final, aviso). Em qualquer situação que impeça a
    normalização (VRAM insuficiente, Ollama fora do ar, resposta inválida),
    retorna o texto original e um aviso explicando o motivo — a síntese nunca
    deve quebrar por causa desse pré-processamento opcional.
    """
    num_ctx = pick_num_ctx()
    if num_ctx is None:
        aviso = (
            "Normalização pulada: não há VRAM livre suficiente para rodar o "
            "Ollama junto com o XTTS-v2 sem risco de travar. Usando o texto original."
        )
        logger.warning(aviso)
        return text, aviso

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
        response = ollama.generate(
            model=model,
            prompt=prompt,
            format="json",
            options={"num_ctx": num_ctx},
        )
        data = json.loads(response["response"])
        normalizado = (data.get("texto_normalizado") or "").strip()
        return normalizado or text, None
    except Exception as e:
        aviso = f"Normalização indisponível (Ollama: {e}). Usando o texto original."
        logger.warning(aviso)
        return text, aviso
