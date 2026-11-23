import copy

import pytest
import torch

from conftest import entrada_mini, dit_mini, precisa_repo, salvar_como_hf, SEM_FLASH
from lct.quantizar import DeltaLora, deltas_da_lora, quantizar_peso, nome_lora


def test_quantizar_peso_igual_oficial(repo):
    from longcat_video.modules.quantization import QuantizedLinear

    lin = torch.nn.Linear(64, 96)
    torch.nn.init.normal_(lin.weight, 0, 0.3)
    ql = QuantizedLinear.from_linear(lin)
    q, s = quantizar_peso(lin.weight.data)
    assert torch.equal(q, ql.weight_int8)
    assert torch.equal(s, ql.weight_scale)


def _forward(dit, x, t, y, mask):
    with torch.no_grad():
        return dit(hidden_states=x, timestep=t, encoder_hidden_states=y, encoder_attention_mask=mask)


@precisa_repo
def test_streaming_igual_quantize_model_oficial(repo, tmp_path):
    """INT8 em streaming + carregamento no meta == quantize_model oficial no modelo inteiro."""
    from longcat_video.modules.quantization import QuantizedLinear, quantize_model
    from lct.carregar import carregar_dit_int8
    from lct.quantizar import quantizar_dit

    ref = dit_mini()
    salvar_como_hf(ref, tmp_path / "dit")
    quantizar_dit(tmp_path / "dit", tmp_path / "int8", log=lambda *_: None)
    meu = carregar_dit_int8(tmp_path / "int8", SEM_FLASH, log=lambda *_: None)

    oficial = quantize_model(copy.deepcopy(ref))
    for m in oficial.modules():
        if not isinstance(m, QuantizedLinear):
            for p in m.parameters(recurse=False):
                p.data = p.data.to(torch.bfloat16)

    a, b = dict(meu.named_buffers()), dict(oficial.named_buffers())
    for k in b:
        if k.endswith("weight_int8") or k.endswith("weight_scale"):
            assert torch.equal(a[k], b[k]), k
    entrada = entrada_mini()
    entrada = (entrada[0].bfloat16(), entrada[1], entrada[2].bfloat16(), entrada[3])
    assert torch.equal(_forward(meu, *entrada), _forward(oficial, *entrada))


@precisa_repo
def test_int8_proximo_do_fp32(repo, tmp_path):
    """Erro da quantização no forward fica pequeno (sanidade, não é medida de qualidade)."""
    from lct.carregar import carregar_dit_int8
    from lct.quantizar import quantizar_dit

    ref = dit_mini()
    salvar_como_hf(ref, tmp_path / "dit")
    quantizar_dit(tmp_path / "dit", tmp_path / "int8", log=lambda *_: None)
    meu = carregar_dit_int8(tmp_path / "int8", SEM_FLASH, log=lambda *_: None)
    x, t, y, m = entrada_mini()
    o_ref = _forward(ref, x, t, y, m)
    o_q = _forward(meu, x.bfloat16(), t, y.bfloat16(), m)
    rel = (o_q - o_ref).norm() / o_ref.norm()
    assert rel < 0.05, rel


def _lora_oficial(modelo, seed=3):
    """LoRA aleatória no formato oficial (rank 128 como no load_lora)."""
    from longcat_video.modules.lora_utils import create_lora_network

    sd = {}
    g = torch.Generator().manual_seed(seed)
    for nome in ["blocks.0.attn.qkv", "blocks.1.ffn.w2", "blocks.2.cross_attn.kv_linear"]:
        lin = modelo.get_submodule(nome)
        ln = nome_lora(nome)
        sd[f"{ln}.lora_down.weight"] = torch.randn(128 * (3 if "qkv" in nome else 1), lin.in_features, generator=g) * 0.02
        if "qkv" in nome:  # n_seperate = 3, como as projeções fundidas
            for i in range(3):
                sd[f"{ln}.lora_up.blocks.{i}.weight"] = torch.randn(lin.out_features // 3, 128, generator=g) * 0.02
        else:
            sd[f"{ln}.lora_up.weight"] = torch.randn(lin.out_features, 128, generator=g) * 0.02
        sd[f"{ln}.alpha_scale"] = torch.tensor(0.5)
    net = create_lora_network(modelo, sd, multiplier=1.0, network_dim=128, network_alpha=64)
    net.load_state_dict(sd, strict=True)
    return sd


@precisa_repo
def test_lora_fundida_igual_lora_em_runtime(repo):
    """W + delta dá o mesmo que o caminho oficial load_lora + enable_loras (fp32, sem quantizar)."""
    from longcat_video.modules.lora_utils import create_lora_network

    ref = dit_mini()
    sd = _lora_oficial(ref)
    ref.lora_dict["x"] = create_lora_network(ref, sd, multiplier=1.0, network_dim=128, network_alpha=64)
    ref.lora_dict["x"].load_state_dict(sd, strict=True)
    ref.enable_loras(["x"])

    fundido = dit_mini()
    with torch.no_grad():
        for mod, d in deltas_da_lora(sd).items():
            fundido.get_submodule(mod).weight += d.matriz()
    x, t, y, m = entrada_mini()
    torch.testing.assert_close(_forward(fundido, x, t, y, m), _forward(ref, x, t, y, m), rtol=1e-4, atol=1e-5)


@precisa_repo
def test_quantizar_com_lora(repo, tmp_path):
    """Variante com LoRA = quantizar o peso já somado; LoRA com módulo inexistente falha."""
    from safetensors.torch import save_file
    from lct.carregar import carregar_dit_int8
    from lct.quantizar import quantizar_dit

    ref = dit_mini()
    salvar_como_hf(ref, tmp_path / "dit")
    sd = _lora_oficial(ref)
    save_file(sd, str(tmp_path / "l.safetensors"))
    quantizar_dit(tmp_path / "dit", tmp_path / "int8", lora=tmp_path / "l.safetensors", log=lambda *_: None)
    meu = carregar_dit_int8(tmp_path / "int8", SEM_FLASH, log=lambda *_: None)
    w = ref.get_submodule("blocks.1.ffn.w2").weight.data + deltas_da_lora(sd)["blocks.1.ffn.w2"].matriz()
    q, s = quantizar_peso(w)
    assert torch.equal(meu.get_submodule("blocks.1.ffn.w2").weight_int8, q)

    sd["lora___lorahyphen___nao___lorahyphen___existe.lora_down.weight"] = torch.zeros(128, 4)
    sd["lora___lorahyphen___nao___lorahyphen___existe.lora_up.weight"] = torch.zeros(4, 128)
    save_file(sd, str(tmp_path / "ruim.safetensors"))
    with pytest.raises(ValueError):
        quantizar_dit(tmp_path / "dit", tmp_path / "int8b", lora=tmp_path / "ruim.safetensors", log=lambda *_: None)


def test_delta_lora_separado():
    down = torch.randn(6, 5)
    ups = [torch.randn(4, 2) for _ in range(3)]
    d = DeltaLora(down, ups, 0.5).matriz()
    x = torch.randn(5)
    esperado = torch.cat([ups[i] @ (down[2 * i:2 * i + 2] @ x) for i in range(3)]) * 0.5
    torch.testing.assert_close(d @ x, esperado)
