import torch

from lct.texto import quantizar_encoder


def test_umt5_int8_roda_e_fica_perto(repo):
    """O forward do UMT5 do transformers funciona com o INT8 (wo fica em bf16)."""
    from transformers import UMT5Config, UMT5EncoderModel
    from longcat_video.modules.quantization import QuantizedLinear

    torch.manual_seed(0)
    cfg = UMT5Config(vocab_size=100, d_model=64, d_kv=16, d_ff=128, num_layers=2, num_heads=4,
                     feed_forward_proj="gated-gelu", is_encoder_decoder=False)
    ref = UMT5EncoderModel(cfg).eval()
    q = UMT5EncoderModel(cfg).eval()
    q.load_state_dict(ref.state_dict())
    quantizar_encoder(q)

    nomes = {n: type(m).__name__ for n, m in q.named_modules()}
    assert nomes["encoder.block.0.layer.1.DenseReluDense.wi_0"] == "QuantizedLinear"
    assert nomes["encoder.block.0.layer.1.DenseReluDense.wo"] == "Linear"
    assert any(isinstance(m, QuantizedLinear) for m in q.modules())

    ids = torch.randint(0, 100, (1, 12))
    mask = torch.ones(1, 12, dtype=torch.int64)
    with torch.no_grad():
        a = ref(ids, mask).last_hidden_state
        b = q(ids, mask).last_hidden_state
    assert ((a - b).norm() / a.norm()) < 0.05
