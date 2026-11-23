"""Prepara o ambiente do LongCat-Video para a RTX 4070 12 GB.

    python preparar.py checar                 # o que falta (GPU, libs, pesos, INT8)
    python preparar.py clonar                 # código oficial no commit testado
    python preparar.py baixar                 # pesos do HF (~78 GiB, retomável)
    python preparar.py quantizar              # INT8 da variante distill (padrão)
    python preparar.py quantizar --variante refino
    python preparar.py quantizar --variante todas
    python preparar.py tudo                   # clonar + baixar + quantizar distill

Pastas (mudam com LONGCAT_PESOS):
    pesos/LongCat-Video/   pesos originais do HF (bf16)
    pesos/int8/dit_<v>/    DiT INT8 por variante (base, distill, refino)
    pesos/cache_texto/     embeddings dos prompts
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from lct import COMMIT_LONGCAT, REPO_LONGCAT, vendor  # noqa: E402

PESOS = Path(os.environ.get("LONGCAT_PESOS", AQUI / "pesos"))
HF_REPO = "meituan-longcat/LongCat-Video"
PASTAS_HF = ["dit/*", "text_encoder/*", "tokenizer/*", "vae/*", "scheduler/*", "lora/*", "*.json", "*.md"]

VARIANTES = {
    "base": None,
    "distill": "lora/cfg_step_lora.safetensors",
    "refino": "lora/refinement_lora.safetensors",
}


def clonar(_args):
    destino = vendor.VENDOR_PADRAO
    if not (destino / ".git").exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", REPO_LONGCAT, str(destino)], check=True)
    subprocess.run(["git", "-C", str(destino), "fetch", "--quiet", "origin"], check=False)
    subprocess.run(["git", "-C", str(destino), "checkout", "--quiet", COMMIT_LONGCAT], check=True)
    print(f"código oficial em {destino} @ {COMMIT_LONGCAT[:7]}")


def baixar(args):
    from huggingface_hub import snapshot_download

    destino = PESOS / "LongCat-Video"
    print(f"baixando {HF_REPO} -> {destino} (retomável)")
    snapshot_download(HF_REPO, local_dir=str(destino), allow_patterns=PASTAS_HF, max_workers=args.workers)
    print("ok")


def quantizar(args):
    from lct.quantizar import quantizar_dit

    origem = PESOS / "LongCat-Video"
    nomes = list(VARIANTES) if args.variante == "todas" else [args.variante]
    for v in nomes:
        destino = PESOS / "int8" / f"dit_{v}"
        if (destino / "quantizacao.json").exists() and not args.refazer:
            print(f"{destino} já existe (use --refazer)")
            continue
        lora = VARIANTES[v]
        print(f"quantizando variante {v}" + (f" com {lora} fundida" if lora else ""))
        quantizar_dit(origem / "dit", destino, lora=(origem / lora) if lora else None)


def _ok(cond, txt, dica=""):
    print(f"  [{'ok' if cond else '--'}] {txt}" + (f"   -> {dica}" if (dica and not cond) else ""))
    return cond


def checar(_args):
    print(f"Python {platform.python_version()} em {platform.system()}")
    tudo = True
    try:
        import torch

        _ok(True, f"torch {torch.__version__} (CUDA {torch.version.cuda})")
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            livre, total = torch.cuda.mem_get_info()
            _ok(True, f"GPU {p.name}, {total / 2**30:.1f} GiB ({livre / 2**30:.1f} livres), sm_{p.major}{p.minor}")
        else:
            tudo &= _ok(False, "CUDA disponível", "instale o torch cu124 (ver README)")
    except ImportError:
        tudo &= _ok(False, "torch instalado", "pip install -r requirements.txt")
    try:
        import psutil

        vm = psutil.virtual_memory()
        _ok(vm.total > 30 * 2**30, f"RAM {vm.total / 2**30:.0f} GiB ({vm.available / 2**30:.0f} livres)",
            "o DiT INT8 ocupa ~13 GiB de RAM e o KV cache ~5 GiB")
    except ImportError:
        pass
    _ok(importlib.util.find_spec("flash_attn") is not None, "flash_attn (opcional)", "sem ele usa SDPA, mais lento")
    tem_triton = importlib.util.find_spec("triton") is not None
    _ok(tem_triton, "triton (precisa para importar o código oficial e para o BSA do refino)",
        "Windows: pip install triton-windows")
    tudo &= tem_triton
    ff = shutil.which("ffmpeg") or importlib.util.find_spec("imageio_ffmpeg")
    tudo &= _ok(bool(ff), "ffmpeg (PATH ou imageio-ffmpeg)")
    tudo &= _ok((vendor.pasta_repo() / "longcat_video").exists(), f"código oficial em {vendor.pasta_repo()}",
                "python preparar.py clonar")
    hf = PESOS / "LongCat-Video"
    for sub in ["dit", "text_encoder", "tokenizer", "vae", "scheduler", "lora"]:
        tudo &= _ok((hf / sub).exists(), f"pesos {sub}/", "python preparar.py baixar")
    for v in VARIANTES:
        _ok((PESOS / "int8" / f"dit_{v}" / "quantizacao.json").exists(), f"INT8 dit_{v}",
            f"python preparar.py quantizar --variante {v}")
    livre = shutil.disk_usage(PESOS if PESOS.exists() else AQUI).free
    _ok(livre > 40 * 2**30, f"disco livre {livre / 2**30:.0f} GiB")
    print("pronto para gerar" if tudo else "falta coisa (ver acima)")
    return 0 if tudo else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("checar")
    sub.add_parser("clonar")
    b = sub.add_parser("baixar")
    b.add_argument("--workers", type=int, default=8)
    q = sub.add_parser("quantizar")
    q.add_argument("--variante", choices=[*VARIANTES, "todas"], default="distill")
    q.add_argument("--refazer", action="store_true")
    t = sub.add_parser("tudo")
    t.add_argument("--workers", type=int, default=8)
    t.add_argument("--com-refino", action="store_true")
    a = ap.parse_args()

    if a.cmd == "checar":
        sys.exit(checar(a))
    if a.cmd == "clonar":
        clonar(a)
    elif a.cmd == "baixar":
        baixar(a)
    elif a.cmd == "quantizar":
        quantizar(a)
    elif a.cmd == "tudo":
        clonar(a)
        baixar(a)
        for v in ["distill"] + (["refino"] if a.com_refino else []):
            quantizar(argparse.Namespace(variante=v, refazer=False))


if __name__ == "__main__":
    main()
