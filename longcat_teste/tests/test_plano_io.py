import json
import subprocess

import numpy as np
import pytest
import torch

from lct import plano, texto, video_io
from lct.carregar import TextoEmCache


def test_plano_90s():
    p = plano.Plano(90)
    assert p.n_segmentos == 17
    assert p.quadros_totais == 1373
    assert p.quadros_totais / 15 >= 90
    assert p.inicio_novos(1) == 93 and p.inicio_novos(2) == 173


@pytest.mark.parametrize("dur,segs", [(2, 1), (6.2, 1), (6.3, 2), (11, 2), (16, 3), (60, 12)])
def test_plano_segmentos(dur, segs):
    assert plano.Plano(dur).n_segmentos == segs


def test_roteiro(tmp_path):
    r = tmp_path / "r.json"
    r.write_text(json.dumps({"trechos": [{"segundos": 30, "prompt": "a"}, {"segundos": 30, "prompt": "b"},
                                         {"prompt": "c"}]}))
    ro = plano.ler_roteiro(r)
    p = plano.Plano(90)
    prompts = [ro.prompt_em(p.inicio_s(s)) for s in range(p.n_segmentos)]
    assert prompts[0] == "a" and prompts[-1] == "c"
    assert prompts.count("a") == 6  # segmentos que começam antes de 30 s: 0, 6.2, 11.5, 16.9, 22.2, 27.5
    assert ro.negativo == plano.NEGATIVO_PADRAO
    assert ro.prompts() == ["a", "b", "c"]


def test_roteiro_invalido(tmp_path):
    r = tmp_path / "r.json"
    r.write_text(json.dumps({"trechos": [{"prompt": "a"}, {"prompt": "b"}]}))
    with pytest.raises(ValueError):
        plano.ler_roteiro(r)
    r.write_text(json.dumps({"trechos": [{"segundos": 5, "prompt": ""}]}))
    with pytest.raises(ValueError):
        plano.ler_roteiro(r)


def test_exemplo_de_roteiro_valido():
    from pathlib import Path

    for arq in (Path(__file__).parent.parent / "roteiros").glob("*.json"):
        plano.ler_roteiro(arq)


def test_texto_em_cache():
    emb = {"p": (torch.ones(1, 1, 4, 8), torch.ones(1, 4, dtype=torch.int64)),
           "": (torch.zeros(1, 1, 4, 8), torch.zeros(1, 4, dtype=torch.int64))}
    tc = TextoEmCache(emb)
    pe, pm, ne, nm = tc("p", do_classifier_free_guidance=False, device="cpu", dtype=torch.bfloat16)
    assert pe.shape == (1, 1, 4, 8) and pe.dtype == torch.bfloat16 and ne is None
    pe, pm, ne, nm = tc("p", negative_prompt=None, device="cpu", dtype=torch.float32)
    assert torch.equal(ne, torch.zeros(1, 1, 4, 8))  # negativo None vira "" como no oficial
    with pytest.raises(KeyError):
        tc("outro", do_classifier_free_guidance=False, device="cpu", dtype=torch.float32)


def test_cache_texto_em_disco(tmp_path):
    t = "um prompt"
    torch.save({"texto": t, "emb": torch.ones(1, 1, 2, 3), "mask": torch.ones(1, 2)}, tmp_path / f"{texto.chave(t)}.pt")
    lido = texto.ler_cache(tmp_path, [t, "outro"])
    assert list(lido) == [t]


def _ffprobe_quadros(arq):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json", str(arq)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"][0]


def test_video_io(tmp_path):
    a = np.random.default_rng(0).random((10, 64, 32, 3)).astype(np.float32)
    video_io.gravar_mp4(a, tmp_path / "a.mp4", 15)
    video_io.gravar_mp4(video_io.para_uint8(a[:6]), tmp_path / "b.mp4", 15)
    video_io.concatenar([tmp_path / "a.mp4", tmp_path / "b.mp4"], tmp_path / "ab.mp4")
    assert int(_ffprobe_quadros(tmp_path / "ab.mp4")["nb_read_frames"]) == 16
    video_io.pos_processar(tmp_path / "ab.mp4", tmp_path / "f.mp4", duracao_s=1.0, fps_final=30, tamanho="36x72")
    info = _ffprobe_quadros(tmp_path / "f.mp4")
    assert (info["width"], info["height"]) == (36, 72)
    assert info["r_frame_rate"] == "30/1"
    assert 28 <= int(info["nb_read_frames"]) <= 31


def test_quadros_estagio1(tmp_path):
    partes = [np.full((n, 2, 2, 3), i, np.uint8) for i, n in enumerate([93, 80, 80])]
    arqs = []
    for i, p in enumerate(partes):
        video_io.salvar_npy(p, tmp_path / f"{i:03d}.npy")
        arqs.append(tmp_path / f"{i:03d}.npy")
    q = video_io.QuadrosEstagio1(arqs)
    assert len(q) == 253
    b = q.intervalo(80, 173)
    assert len(b) == 93 and b[0, 0, 0, 0] == 0 and b[13, 0, 0, 0] == 1 and b[-1, 0, 0, 0] == 1
    assert len(q.intervalo(160, 253)) == 93


def test_estado(tmp_path):
    e = video_io.Estado(tmp_path)
    e.set(a=1)
    assert video_io.Estado(tmp_path).get("a") == 1
