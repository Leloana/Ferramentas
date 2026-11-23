"""Testes em CPU, sem pesos reais: usam um DiT minúsculo do código oficial.

Precisam do código oficial (``python preparar.py clonar`` ou ``LONGCAT_REPO``);
sem ele, os testes que dependem dele são pulados.
"""

import json
import sys
from pathlib import Path

import pytest
import torch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from lct import vendor  # noqa: E402

TEM_REPO = (vendor.pasta_repo() / "longcat_video" / "pipeline_longcat_video.py").exists()
precisa_repo = pytest.mark.skipif(not TEM_REPO, reason="código oficial não clonado (preparar.py clonar)")

# mesma estrutura do real (head_dim 128, patch 1x2x2), só que pequeno
CONFIG_MINI = {
    "_class_name": "LongCatVideoTransformer3DModel",
    "_diffusers_version": "0.32.0",
    "adaln_tembed_dim": 32,
    "bsa_params": {"sparsity": 0.9375, "chunk_3d_shape_q": [4, 4, 4], "chunk_3d_shape_k": [4, 4, 4]},
    "caption_channels": 64,
    "cp_split_hw": None,
    "depth": 3,
    "enable_bsa": False,
    "enable_flashattn3": False,
    "enable_flashattn2": True,
    "frequency_embedding_size": 32,
    "hidden_size": 256,
    "in_channels": 4,
    "text_tokens_zero_pad": True,
    "mlp_ratio": 4,
    "num_heads": 2,
    "out_channels": 4,
    "patch_size": [1, 2, 2],
}

SEM_FLASH = {"enable_flashattn3": False, "enable_flashattn2": False, "enable_xformers": False}


@pytest.fixture(scope="session")
def repo():
    if not TEM_REPO:
        pytest.skip("código oficial não clonado")
    vendor.garantir_no_path()
    from lct import patches

    patches.aplicar_sdpa()
    return vendor.pasta_repo()


def dit_mini(seed=0, dtype=torch.float32, config=CONFIG_MINI):
    from lct.carregar import config_construtor
    from longcat_video.modules.longcat_video_dit import LongCatVideoTransformer3DModel

    torch.manual_seed(seed)
    m = LongCatVideoTransformer3DModel(**config_construtor(config, SEM_FLASH))
    with torch.no_grad():
        for p in m.parameters():  # init aleatória visível (vários pesos começam zerados)
            p.normal_(0, 0.05)
    return m.to(dtype).eval()


def salvar_como_hf(modelo, pasta: Path, n_shards=2, config=CONFIG_MINI):
    """Grava como a pasta dit/ do HF: fp32, em shards, com index e config."""
    from safetensors.torch import save_file

    pasta.mkdir(parents=True, exist_ok=True)
    sd = {k: v.detach().float().contiguous() for k, v in modelo.state_dict().items()}
    chaves = sorted(sd)
    mapa = {}
    for i in range(n_shards):
        parte = chaves[i::n_shards]
        nome = f"diffusion_pytorch_model-{i + 1:05d}-of-{n_shards:05d}.safetensors"
        save_file({k: sd[k] for k in parte}, str(pasta / nome))
        mapa.update({k: nome for k in parte})
    (pasta / "diffusion_pytorch_model.safetensors.index.json").write_text(json.dumps({"weight_map": mapa}))
    (pasta / "config.json").write_text(json.dumps(config))


def entrada_mini(seed=1, B=1, T=3, H=8, W=8, n_txt=7):
    g = torch.Generator().manual_seed(seed)
    x = torch.randn(B, CONFIG_MINI["in_channels"], T, H, W, generator=g)
    t = torch.full((B,), 500.0)
    y = torch.randn(B, 1, 16, CONFIG_MINI["caption_channels"], generator=g)
    mask = torch.zeros(B, 16, dtype=torch.int64)
    mask[:, :n_txt] = 1
    return x, t, y, mask
