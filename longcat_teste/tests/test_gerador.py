"""Ponta a ponta em CPU: pipeline OFICIAL do LongCat com modelos minúsculos.

Roda o caminho inteiro do gerar.py (quantização, carregamento no meta,
offload, texto em cache, t2v, 2 continuações com KV cache, retomada,
concatenação e pós) sem pesos reais. Só o UMT5 não roda: o cache de texto é
pré-populado com embeddings aleatórios.
"""

import json

import numpy as np
import pytest
import torch

from conftest import CONFIG_MINI, dit_mini, salvar_como_hf
from lct import texto
from lct.gerador import Gerador, Opcoes
from lct.plano import roteiro_de_prompt

PROMPT = "a dog runs on the beach"


@pytest.fixture
def ambiente(repo, tmp_path, monkeypatch):
    from longcat_video.modules.autoencoder_kl_wan import AutoencoderKLWan
    from longcat_video.modules.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
    from lct.quantizar import quantizar_dit

    # conv3d em bf16 na CPU é ~20x mais lenta (223 s por decode). Só no teste:
    # o VAE calcula em fp32 e devolve no dtype de quem chamou. Na GPU fica bf16.
    enc, dec = AutoencoderKLWan.encode, AutoencoderKLWan.decode

    def encode_fp32(self, x, *a, **k):
        self.float()
        return enc(self, x.float(), *a, **k)

    def decode_fp32(self, z, *a, **k):
        self.float()
        return dec(self, z.float(), *a, **k)

    monkeypatch.setattr(AutoencoderKLWan, "encode", encode_fp32)
    monkeypatch.setattr(AutoencoderKLWan, "decode", decode_fp32)
    # o refino oficial chama torch.cuda.ipc_collect(), que não existe no torch de CPU
    import longcat_video.pipeline_longcat_video as plv

    monkeypatch.setattr(plv, "torch_gc", lambda: None)

    cfg = {**CONFIG_MINI, "in_channels": 16, "out_channels": 16}
    raiz = tmp_path / "pesos"
    hf = raiz / "LongCat-Video"
    salvar_como_hf(dit_mini(config=cfg), hf / "dit", config=cfg)
    quantizar_dit(hf / "dit", raiz / "int8" / "dit_distill", log=lambda *_: None)
    quantizar_dit(hf / "dit", raiz / "int8" / "dit_refino", log=lambda *_: None)
    torch.manual_seed(0)
    AutoencoderKLWan(base_dim=8, num_res_blocks=1).save_pretrained(hf / "vae")
    FlowMatchEulerDiscreteScheduler(shift=12.0).save_pretrained(hf / "scheduler")
    (hf / "text_encoder").mkdir()
    (hf / "text_encoder" / "config.json").write_text(json.dumps({"d_model": cfg["caption_channels"]}))

    cache = raiz / "cache_texto"
    cache.mkdir()
    g = torch.Generator().manual_seed(5)
    mask = torch.zeros(1, 512, dtype=torch.int64)
    mask[:, :9] = 1
    emb = torch.randn(1, 1, 512, cfg["caption_channels"], generator=g).bfloat16()
    torch.save({"texto": PROMPT, "emb": emb, "mask": mask}, cache / f"{texto.chave(PROMPT)}.pt")
    return raiz


def _opcoes(raiz, saida, **kw):
    base = dict(pesos=raiz / "LongCat-Video", int8=raiz / "int8", saida=saida, roteiro=roteiro_de_prompt(PROMPT),
                duracao_s=2.0, quadros=21, passos=3, blocos_na_gpu="1", pin=False, atencao="sdpa",
                tamanho_final="90x160", fps_final=30)
    base.update(kw)
    return Opcoes(**base)


def test_ponta_a_ponta_e_retomada(ambiente, tmp_path):
    saida = tmp_path / "out"
    # para no 2º segmento (como uma queda) e guarda a condição que o 3º vai usar
    Gerador(_opcoes(ambiente, saida, max_segmentos=2), log=lambda *_: None).rodar()
    cond_apos_2 = np.load(saida / "cond.npy")
    assert cond_apos_2.shape[0] == 13

    op = _opcoes(ambiente, saida)
    g = Gerador(op, log=lambda *_: None)
    assert g.plano.n_segmentos == 3  # 21 + 2 x 8 >= 30 quadros
    final = g.rodar()  # retoma: só gera o 3º
    assert final.exists() and final.stat().st_size > 0

    est = json.loads((saida / "estado.json").read_text())
    assert est["estagio1_feitos"] == 3
    tamanhos = [len(np.load(saida / "quadros" / f"{i:03d}.npy")) for i in range(3)]
    assert tamanhos == [21, 8, 8]
    assert np.load(saida / "quadros" / "000.npy").shape[1:] == (832, 480, 3)  # vertical
    med = [json.loads(l) for l in (saida / "medicoes.jsonl").read_text().splitlines()]
    assert sum(1 for m in med if m["etapa"] == "estagio1") == 3  # 2 na 1ª rodada + 1 na retomada

    # refazer o 3º a partir do mesmo estado dá o mesmo vídeo (seed por segmento + cond salvo)
    antes = np.load(saida / "quadros" / "002.npy")
    (saida / "quadros" / "002.npy").unlink()
    np.save(saida / "cond.npy", cond_apos_2)
    est["estagio1_feitos"] = 2
    (saida / "estado.json").write_text(json.dumps(est))
    Gerador(op, log=lambda *_: None).rodar()
    depois = np.load(saida / "quadros" / "002.npy")
    assert np.array_equal(antes, depois)

    # e rodar de novo com tudo pronto não gera nada
    n = len((saida / "medicoes.jsonl").read_text().splitlines())
    Gerador(op, log=lambda *_: None).rodar()
    novas = [json.loads(l) for l in (saida / "medicoes.jsonl").read_text().splitlines()[n:]]
    assert not any(m["etapa"] == "estagio1" for m in novas)


def test_opcoes_diferentes_nao_misturam(ambiente, tmp_path):
    saida = tmp_path / "out"
    Gerador(_opcoes(ambiente, saida, duracao_s=1.0), log=lambda *_: None).rodar()
    with pytest.raises(SystemExit):
        Gerador(_opcoes(ambiente, saida, duracao_s=1.0, seed=7), log=lambda *_: None).rodar()
    Gerador(_opcoes(ambiente, saida, duracao_s=1.0, seed=7, recomecar=True), log=lambda *_: None).rodar()


def _info(arq):
    import subprocess

    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames,width,height", "-of", "json", str(arq)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"][0]


def test_refino_espacial(ambiente, tmp_path):
    """Troca para o dit_refino, lê o estágio 1 por intervalo e encadeia a condição (atenção densa)."""
    # o refino usa prompt vazio: entra no cache como o gerador pediria ao UMT5
    cache = ambiente / "cache_texto"
    d = torch.load(cache / f"{texto.chave(PROMPT)}.pt", weights_only=True)
    torch.save({"texto": "", "emb": torch.zeros_like(d["emb"]), "mask": d["mask"]}, cache / f"{texto.chave('')}.pt")

    saida = tmp_path / "out"
    op = _opcoes(ambiente, saida, duracao_s=1.5, refino="espacial", refino_bsa=False, refino_passos=2)
    final = Gerador(op, log=lambda *_: None).rodar()
    est = json.loads((saida / "estado.json").read_text())
    assert est["estagio1_feitos"] == 2 and est["refino_feitos"] == 2
    r0, r1 = _info(saida / "refino" / "000.mp4"), _info(saida / "refino" / "001.mp4")
    assert (int(r0["width"]), int(r0["height"])) == (704, 1280)  # bucket 720p vertical
    assert int(r0["nb_read_frames"]) == 21 and int(r1["nb_read_frames"]) == 8
    assert final.exists()
