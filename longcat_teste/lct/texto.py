"""Codifica os prompts com o UMT5-XXL uma vez e guarda em disco.

O text encoder do LongCat (UMT5-XXL, ~5,7B parâmetros, ~11 GiB em bf16) não
pode ficar na memória junto com o DiT. Então ele roda antes de tudo, gera os
embeddings de todos os prompts do roteiro (mais o negativo e o vazio do
refino), grava em ``cache_texto/<sha>.pt`` e sai da memória.

Modos:
    int8-gpu (padrão): lineares em INT8 (menos a wo da FFN), ~7,7 GiB na GPU
    bf16-cpu: exato, na CPU. Mais lento (ordem de minutos por prompt, não medido)
"""

from __future__ import annotations

import gc
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, Tuple

import torch

from . import vendor

MAX_TOKENS = 512


def chave(texto: str) -> str:
    return hashlib.sha256(f"{MAX_TOKENS}|{texto}".encode("utf-8")).hexdigest()[:24]


def _caminho(cache: Path, texto: str) -> Path:
    return Path(cache) / f"{chave(texto)}.pt"


def ler_cache(cache: Path, textos: Iterable[str]) -> Dict[str, Tuple[torch.Tensor, torch.Tensor]]:
    out = {}
    for t in textos:
        p = _caminho(cache, t)
        if p.exists():
            d = torch.load(p, map_location="cpu", weights_only=True)
            if d.get("texto") == t:
                out[t] = (d["emb"], d["mask"])
    return out


def quantizar_encoder(te):
    """Lineares do UMT5 em INT8, menos a ``wo`` da FFN.

    A FFN do T5 no transformers lê ``self.wo.weight.dtype`` (o QuantizedLinear não
    tem ``.weight``), e a ``wo`` é a camada do T5 conhecida por estourar em baixa
    precisão. Fica em bf16: ~2 GiB, total na GPU ~7,7 GiB.
    """
    vendor.garantir_no_path()
    from longcat_video.modules.quantization import quantize_model

    return quantize_model(te, skip_patterns={"DenseReluDense.wo"})


def codificar(pesos: Path, textos: Iterable[str], cache: Path, modo: str = "int8-gpu", log=print):
    """Devolve {texto: (emb [1,1,512,d] bf16 cpu, mask [1,512])}; codifica só o que falta."""
    textos = list(dict.fromkeys(textos))
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    prontos = ler_cache(cache, textos)
    faltam = [t for t in textos if t not in prontos]
    if not faltam:
        log(f"texto: {len(textos)} prompts já em cache")
        return prontos

    vendor.garantir_no_path()
    from transformers import AutoTokenizer, UMT5EncoderModel
    from longcat_video.pipeline_longcat_video import LongCatVideoPipeline

    log(f"texto: codificando {len(faltam)} prompts ({modo})")
    tok = AutoTokenizer.from_pretrained(pesos, subfolder="tokenizer")
    te = UMT5EncoderModel.from_pretrained(pesos, subfolder="text_encoder",
                                          torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    te.eval().requires_grad_(False)
    if modo == "int8-gpu":
        quantizar_encoder(te)
        device = "cuda"
        te.to(device)
    elif modo == "bf16-cpu":
        device = "cpu"
    else:
        raise SystemExit(f"--texto desconhecido: {modo}")

    # usa a mesma limpeza/tokenização do pipeline oficial
    fake = SimpleNamespace(tokenizer=tok, text_encoder=te)
    try:
        for t in faltam:
            with torch.no_grad():
                emb, mask = LongCatVideoPipeline._get_t5_prompt_embeds(
                    fake, prompt=t, max_sequence_length=MAX_TOKENS, device=device, dtype=torch.bfloat16)
            emb, mask = emb.cpu(), mask.cpu()
            torch.save({"texto": t, "emb": emb, "mask": mask}, _caminho(cache, t))
            prontos[t] = (emb, mask)
            log(f"  ok: {t[:70]!r}")
    finally:
        del te, fake
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return prontos
