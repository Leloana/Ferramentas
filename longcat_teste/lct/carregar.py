"""Monta o DiT INT8 e o pipeline do LongCat-Video sem estourar a RAM.

- O modelo é instanciado no device ``meta`` (nenhum byte alocado), as lineares
  listadas em ``quantizacao.json`` viram ``QuantizedLinear`` (classe oficial) e
  os shards são carregados um a um com ``assign=True``.
- O pipeline recebe um "text encoder" de mentira: os prompts já foram
  codificados por ``lct.texto`` e o ``encode_prompt`` passa a ler do cache.
- Nada de ``pipe.to(cuda)``: quem põe o DiT na GPU é ``lct.offload``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional, Tuple

import torch

from . import vendor

CHAVES_NAO_CONSTRUTOR = ("_class_name", "architectures", "_diffusers_version", "model_max_length", "_name_or_path")


def config_construtor(config: dict, atencao: Optional[dict] = None) -> dict:
    cfg = {k: v for k, v in config.items() if k not in CHAVES_NAO_CONSTRUTOR}
    cfg["cp_split_hw"] = [1, 1]  # sem paralelismo de contexto: 1 GPU
    if atencao:
        cfg.update(atencao)
    return cfg


def instanciar_dit_meta(config: dict, atencao: Optional[dict] = None):
    vendor.garantir_no_path()
    from longcat_video.modules.longcat_video_dit import LongCatVideoTransformer3DModel

    with torch.device("meta"):
        return LongCatVideoTransformer3DModel(**config_construtor(config, atencao))


def _trocar_por_quantizada(dit, nomes):
    from longcat_video.modules.quantization import QuantizedLinear

    for nome in nomes:
        pai_nome, _, filho = nome.rpartition(".")
        pai = dit.get_submodule(pai_nome) if pai_nome else dit
        lin = getattr(pai, filho)
        if not isinstance(lin, torch.nn.Linear):
            raise TypeError(f"{nome} não é nn.Linear ({type(lin).__name__})")
        with torch.device("meta"):
            ql = QuantizedLinear(lin.in_features, lin.out_features, bias=lin.bias is not None)
        setattr(pai, filho, ql)


def tensores_meta(modulo: torch.nn.Module):
    ruins = [n for n, p in modulo.named_parameters() if p.is_meta]
    ruins += [n for n, b in modulo.named_buffers() if b.is_meta]
    return ruins


def carregar_dit_int8(pasta: Path, atencao: Optional[dict] = None, log=print):
    """Carrega uma pasta gerada por ``lct.quantizar.quantizar_dit`` na CPU."""
    from safetensors.torch import load_file

    pasta = Path(pasta)
    config = json.loads((pasta / "config.json").read_text())
    resumo = json.loads((pasta / "quantizacao.json").read_text())
    dit = instanciar_dit_meta(config, atencao)
    _trocar_por_quantizada(dit, resumo["quantizados"])

    mapa = json.loads((pasta / "dit-int8.safetensors.index.json").read_text())["weight_map"]
    esperadas = set(dit.state_dict().keys())
    vistas = set()
    for shard in sorted(set(mapa.values())):
        sd = load_file(str(pasta / shard), device="cpu")
        inesperadas = set(sd) - esperadas
        if inesperadas:
            raise KeyError(f"{shard}: chaves que o modelo não tem, ex.: {sorted(inesperadas)[:3]}")
        dit.load_state_dict(sd, strict=False, assign=True)
        vistas |= set(sd)
        del sd
        log(f"  {shard} carregado")
    faltam = esperadas - vistas
    if faltam:
        raise KeyError(f"faltam {len(faltam)} pesos no INT8, ex.: {sorted(faltam)[:3]}")
    meta = tensores_meta(dit)
    if meta:
        raise RuntimeError(f"tensores ainda no meta depois de carregar: {meta[:5]}")

    # mesmo critério do load_quantized_dit oficial: o que é float vira bf16,
    # buffers int8/escala fp32 do QuantizedLinear ficam como estão
    from longcat_video.modules.quantization import QuantizedLinear

    for m in dit.modules():
        if isinstance(m, QuantizedLinear):
            continue
        for p in m.parameters(recurse=False):
            if p.dtype == torch.float32:
                p.data = p.data.to(torch.bfloat16)
    dit.eval().requires_grad_(False)
    return dit


# --------------------------------------------------------------------------- #
# Texto em cache no lugar do UMT5
# --------------------------------------------------------------------------- #

class TextoEmCache:
    """Substitui ``pipe.encode_prompt``; os embeddings vêm de ``lct.texto``."""

    def __init__(self, embeddings: Dict[str, Tuple[torch.Tensor, torch.Tensor]]):
        self.embeddings = embeddings

    def _um(self, texto, device, dtype, n):
        if texto not in self.embeddings:
            raise KeyError(f"prompt sem embedding em cache (codifique antes): {texto[:80]!r}")
        emb, mask = self.embeddings[texto]
        emb = emb.to(device=device, dtype=dtype)
        mask = mask.to(device=device)
        if n > 1:
            emb = emb.repeat(n, 1, 1, 1)
            mask = mask.repeat(n, 1)
        return emb, mask

    def __call__(self, prompt, negative_prompt=None, do_classifier_free_guidance=True,
                 num_videos_per_prompt=1, max_sequence_length=512, device=None, dtype=None):
        prompts = [prompt] if isinstance(prompt, str) else list(prompt)
        pe, pm = zip(*(self._um(p, device, dtype, num_videos_per_prompt) for p in prompts))
        pe, pm = torch.cat(pe), torch.cat(pm)
        if not do_classifier_free_guidance:
            return pe, pm, None, None
        neg = negative_prompt or ""
        negs = len(prompts) * [neg] if isinstance(neg, str) else list(neg)
        ne, nm = zip(*(self._um(p, device, dtype, num_videos_per_prompt) for p in negs))
        return pe, pm, torch.cat(ne), torch.cat(nm)


def stub_text_encoder(d_model: int = 4096, dtype=torch.bfloat16):
    """O pipeline só lê ``text_encoder.config.d_model`` e ``.dtype`` fora do encode_prompt."""
    return SimpleNamespace(config=SimpleNamespace(d_model=d_model), dtype=dtype)


def montar_pipeline(pesos: Path, dit, embeddings, device="cuda", vae_tiling=False):
    """Pipeline oficial com VAE/scheduler do HF, DiT já carregado e texto em cache."""
    vendor.garantir_no_path()
    from longcat_video.modules.autoencoder_kl_wan import AutoencoderKLWan
    from longcat_video.modules.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
    from longcat_video.pipeline_longcat_video import LongCatVideoPipeline

    pesos = Path(pesos)
    vae = AutoencoderKLWan.from_pretrained(pesos, subfolder="vae", torch_dtype=torch.bfloat16)
    if vae_tiling:
        vae.enable_tiling()
    sched = FlowMatchEulerDiscreteScheduler.from_pretrained(pesos, subfolder="scheduler", torch_dtype=torch.bfloat16)
    d_model = json.loads((pesos / "text_encoder" / "config.json").read_text()).get("d_model", 4096)

    pipe = LongCatVideoPipeline(
        tokenizer=None,
        text_encoder=stub_text_encoder(d_model),
        vae=vae.to(device),
        scheduler=sched,
        dit=dit,
    )
    pipe.device = device
    pipe.encode_prompt = TextoEmCache(embeddings)
    return pipe
