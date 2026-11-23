"""Ajustes no código oficial para rodar numa GPU só, no Windows, com 12 GB.

1. Atenção via ``torch.nn.functional.scaled_dot_product_attention`` quando não
   há flash-attn/xformers. O código oficial só tem flash-attn 2/3, xformers e
   BSA (triton); sem eles levanta "Unsupported attention operations". No
   Windows, flash-attn exige wheel compilada para a combinação exata de
   torch/CUDA/Python, então o SDPA (kernel memory-efficient do PyTorch) é o
   caminho padrão. O BSA do refino continua o oficial (precisa de triton).
2. FFN SwiGLU em pedaços de tokens: no refino 720p a camada intermediária
   (~11k canais x 85k tokens) passa de 1,8 GiB por tensor. Em pedaços o pico
   cai para o tamanho de um pedaço; o resultado é o mesmo.
3. Sem ``torch.distributed``: com ``cp_size == 1`` o código oficial já pula as
   comunicações, só não pode chamar ``init_context_parallel``. Nada a fazer
   além de passar ``cp_split_hw=[1, 1]`` (ver ``lct.carregar``).
"""

from __future__ import annotations

import importlib.util

import torch
import torch.nn.functional as F

from . import vendor

_aplicados = set()


def tem_flash_attn() -> bool:
    return importlib.util.find_spec("flash_attn") is not None


def tem_xformers() -> bool:
    return importlib.util.find_spec("xformers") is not None


def escolher_atencao(pedido: str = "auto") -> dict:
    """Flags de atenção para o config do DiT."""
    flags = {"enable_flashattn3": False, "enable_flashattn2": False, "enable_xformers": False}
    if pedido == "auto":
        pedido = "flash2" if tem_flash_attn() else "sdpa"
    if pedido == "flash2":
        if not tem_flash_attn():
            raise SystemExit("--atencao flash2 pedido, mas flash_attn não está instalado")
        flags["enable_flashattn2"] = True
    elif pedido == "xformers":
        if not tem_xformers():
            raise SystemExit("--atencao xformers pedido, mas xformers não está instalado")
        flags["enable_xformers"] = True
    elif pedido != "sdpa":
        raise SystemExit(f"--atencao desconhecida: {pedido}")
    return flags


# --------------------------------------------------------------------------- #
# 1. SDPA
# --------------------------------------------------------------------------- #

def _sem_backend(mod) -> bool:
    return not (mod.enable_flashattn3 or mod.enable_flashattn2 or mod.enable_xformers)


def aplicar_sdpa():
    if "sdpa" in _aplicados:
        return
    vendor.garantir_no_path()
    from longcat_video.modules import attention as att

    orig_self = att.Attention._process_attn
    orig_cross = att.MultiHeadCrossAttention._process_cross_attn

    def _process_attn(self, q, k, v, shape):
        # BSA (refino) e backends oficiais seguem o caminho original
        if (self.enable_bsa and shape[0] > 1) or not _sem_backend(self):
            return orig_self(self, q, k, v, shape)
        # q, k, v: [B, H, S, D]; cp_size == 1, então o ulysses não faz nada
        return F.scaled_dot_product_attention(q, k, v, scale=self.scale)

    def _process_cross_attn(self, x, cond, kv_seqlen):
        if not _sem_backend(self):
            return orig_cross(self, x, cond, kv_seqlen)
        B, N, C = x.shape
        assert C == self.dim and cond.shape[2] == self.dim
        q = self.q_linear(x).view(1, -1, self.num_heads, self.head_dim)
        kv = self.kv_linear(cond).view(1, -1, 2, self.num_heads, self.head_dim)
        k, v = kv.unbind(2)
        q, k = self.q_norm(q), self.k_norm(k)
        # equivalente ao flash_attn_varlen_func: item b atende só aos seus tokens de texto
        saidas = []
        ini = 0
        for b in range(B):
            fim = ini + int(kv_seqlen[b])
            qb = q[0, b * N:(b + 1) * N].transpose(0, 1).unsqueeze(0)   # [1, H, N, D]
            kb = k[0, ini:fim].transpose(0, 1).unsqueeze(0)
            vb = v[0, ini:fim].transpose(0, 1).unsqueeze(0)
            ob = F.scaled_dot_product_attention(qb, kb, vb)          # escala padrão = flash
            saidas.append(ob[0].transpose(0, 1))                     # [N, H, D]
            ini = fim
        x = torch.cat(saidas, dim=0).reshape(B, -1, C)
        return self.proj(x)

    # mantém o ulysses_wrapper oficial (não faz nada com cp_size 1)
    from longcat_video.context_parallel.ulysses_wrapper import ulysses_wrapper

    att.Attention._process_attn = ulysses_wrapper(_process_attn)
    att.MultiHeadCrossAttention._process_cross_attn = _process_cross_attn
    _aplicados.add("sdpa")


# --------------------------------------------------------------------------- #
# 2. FFN em pedaços
# --------------------------------------------------------------------------- #

_ffn_pedaco = {"tokens": 0}


def aplicar_ffn_em_pedacos(tokens: int):
    """``tokens`` = tamanho do pedaço na dimensão de sequência (0 desliga)."""
    _ffn_pedaco["tokens"] = int(tokens)
    if "ffn" in _aplicados:
        return
    vendor.garantir_no_path()
    from longcat_video.modules import blocks

    orig = blocks.FeedForwardSwiGLU.forward

    def forward(self, x):
        n = _ffn_pedaco["tokens"]
        if n <= 0 or x.dim() != 3 or x.shape[1] <= n:
            return orig(self, x)
        return torch.cat([orig(self, x[:, i:i + n]) for i in range(0, x.shape[1], n)], dim=1)

    blocks.FeedForwardSwiGLU.forward = forward
    _aplicados.add("ffn")


def aplicar_tudo(ffn_tokens: int = 16384):
    aplicar_sdpa()
    aplicar_ffn_em_pedacos(ffn_tokens)
