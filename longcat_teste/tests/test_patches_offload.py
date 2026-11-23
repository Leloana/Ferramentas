import copy

import torch

from conftest import SEM_FLASH, dit_mini, entrada_mini


def _ingenua(q, k, v, escala):
    a = (q.float() @ k.float().transpose(-1, -2)) * escala
    return (a.softmax(-1) @ v.float()).to(q.dtype)


def test_sdpa_self_attention(repo):
    from longcat_video.modules.attention import Attention

    att = Attention(256, 2, cp_split_hw=[1, 1], **SEM_FLASH)
    g = torch.Generator().manual_seed(0)
    q, k, v = (torch.randn(2, 2, 40, 128, generator=g) for _ in range(3))
    out = att._process_attn(q, k, v, (1, 5, 8))
    torch.testing.assert_close(out, _ingenua(q, k, v, att.scale), rtol=1e-4, atol=1e-5)


def test_sdpa_cross_attention_varlen(repo):
    """Cada item do lote só enxerga os seus tokens de texto (como flash varlen)."""
    from longcat_video.modules.attention import MultiHeadCrossAttention

    torch.manual_seed(0)
    ca = MultiHeadCrossAttention(256, 2, **SEM_FLASH).eval()
    B, N, lens = 2, 10, [3, 5]
    x = torch.randn(B, N, 256)
    cond = torch.randn(1, sum(lens), 256)
    out = ca._process_cross_attn(x, cond, lens)

    q = ca.q_norm(ca.q_linear(x).view(B, N, 2, 128))
    kv = ca.kv_linear(cond).view(1, -1, 2, 2, 128)
    k, v = kv.unbind(2)
    k = ca.k_norm(k)
    esperado, ini = [], 0
    for b in range(B):
        kb, vb = k[0, ini:ini + lens[b]], v[0, ini:ini + lens[b]]
        ob = _ingenua(q[b].transpose(0, 1), kb.transpose(0, 1), vb.transpose(0, 1), 128 ** -0.5)
        esperado.append(ob.transpose(0, 1).reshape(N, 256))
        ini += lens[b]
    esperado = ca.proj(torch.stack(esperado))
    torch.testing.assert_close(out, esperado, rtol=1e-4, atol=1e-5)


def test_ffn_em_pedacos_igual(repo):
    from longcat_video.modules.blocks import FeedForwardSwiGLU
    from lct import patches

    ffn = FeedForwardSwiGLU(64, 256)
    x = torch.randn(2, 103, 64)
    patches.aplicar_ffn_em_pedacos(0)
    inteiro = ffn(x)
    patches.aplicar_ffn_em_pedacos(16)
    try:
        torch.testing.assert_close(ffn(x), inteiro)
    finally:
        patches.aplicar_ffn_em_pedacos(0)


def test_offload_mesmo_resultado_e_devolve_para_ram(repo):
    from lct.offload import OffloadPorBloco

    ref = dit_mini()
    dit = copy.deepcopy(ref)
    off = OffloadPorBloco(dit, "cpu", blocos_na_gpu=1, pin=False, log=lambda *_: None)
    assert off.passagem == [1, 2]
    x, t, y, m = entrada_mini()
    with torch.no_grad():
        a = ref(hidden_states=x, timestep=t, encoder_hidden_states=y, encoder_attention_mask=m)
        b = dit(hidden_states=x, timestep=t, encoder_hidden_states=y, encoder_attention_mask=m)
        c = dit(hidden_states=x, timestep=t, encoder_hidden_states=y, encoder_attention_mask=m)  # 2ª passada (prefetch circular)
    torch.testing.assert_close(a, b)
    torch.testing.assert_close(a, c)
    # depois do forward os blocos de passagem apontam de volta para a cópia da RAM
    for i in off.passagem:
        atuais = [s[0]._parameters[s[1]] if s[2] else s[0]._buffers[s[1]] for s in off.slots[i]]
        assert all(t_.data_ptr() == c_.data_ptr() for t_, c_ in zip(atuais, off.na_cpu[i]))
    off.remover()
    assert not off.handles


def test_blocos_que_cabem():
    from lct.offload import blocos_que_cabem

    G = 2**30
    assert blocos_que_cabem(11 * G, 270 * 2**20, int(4.5 * G)) == 22
    assert blocos_que_cabem(4 * G, 270 * 2**20, 5 * G) == 0
