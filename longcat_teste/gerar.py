"""Gera um vídeo longo (padrão: 90 s vertical) com o LongCat-Video INT8 numa GPU de 12 GB.

Exemplos:
    python gerar.py --prompt "a woman walks her dog on a beach at sunset, handheld camera" --saida output/praia
    python gerar.py --roteiro roteiros/exemplo_90s.json --saida output/roteiro
    python gerar.py --imagem foto.png --prompt "..." --saida output/foto      # 1º segmento a partir da imagem
    python gerar.py ... --refino espacial                                      # experimental, ver README

Rodar de novo o mesmo comando retoma de onde parou.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from lct.gerador import Gerador, Opcoes  # noqa: E402
from lct.plano import ler_roteiro, roteiro_de_prompt  # noqa: E402

PESOS = Path(os.environ.get("LONGCAT_PESOS", AQUI / "pesos"))


def argumentos(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("conteúdo")
    x = g.add_mutually_exclusive_group(required=True)
    x.add_argument("--prompt", help="prompt único (em inglês rende melhor)")
    x.add_argument("--roteiro", type=Path, help="JSON com prompts por trecho (ver roteiros/)")
    g.add_argument("--negativo", help="substitui o negativo padrão (só vale no modo completo)")
    g.add_argument("--imagem", type=Path, help="começa o vídeo desta imagem (recorte central 9:16)")
    g.add_argument("--duracao", type=float, default=90.0, help="segundos (padrão 90)")
    g.add_argument("--formato", choices=["vertical", "horizontal"], default="vertical")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--saida", type=Path, required=True)

    g = ap.add_argument_group("qualidade x tempo")
    g.add_argument("--modo", choices=["distill", "completo"], default="distill",
                   help="distill: 16 passos sem CFG (padrão). completo: 50 passos CFG 4, ~6x mais lento")
    g.add_argument("--passos", type=int)
    g.add_argument("--cfg", type=float)
    g.add_argument("--quadros", type=int, default=93, help="quadros por segmento (4k+1; testes usam menos)")
    g.add_argument("--max-segmentos", type=int, help="para no N-ésimo segmento (teste)")
    g.add_argument("--refino", choices=["nenhum", "espacial", "completo"], default="nenhum",
                   help="refino oficial para 720p. espacial: mantém 15 fps. completo: 720p 30 fps (não deve caber em 12 GB)")
    g.add_argument("--refino-passos", type=int, default=50)
    g.add_argument("--refino-sem-bsa", action="store_true", help="refino com atenção densa (sem triton/BSA)")

    g = ap.add_argument_group("memória")
    g.add_argument("--blocos-na-gpu", default="auto", help="blocos do DiT fixos na GPU (0-48) ou auto")
    g.add_argument("--reserva-gib", type=float, help="VRAM reservada para ativações no modo auto")
    g.add_argument("--sem-pin", action="store_true", help="não usa pinned memory (se o Windows reclamar)")
    g.add_argument("--atencao", choices=["auto", "sdpa", "flash2", "xformers"], default="auto")
    g.add_argument("--ffn-tokens", type=int, default=16384, help="pedaço da FFN em tokens (0 desliga)")
    g.add_argument("--texto", choices=["int8-gpu", "bf16-cpu"], default="int8-gpu")
    g.add_argument("--kv-cache-gpu", action="store_true", help="KV cache da condição na GPU (+~5 GiB)")
    g.add_argument("--vae-tiling", action="store_true")

    g = ap.add_argument_group("pós (ffmpeg)")
    g.add_argument("--tamanho-final", default="720x1280", help="LxA do final.mp4 ('' mantém)")
    g.add_argument("--fps-final", type=int, default=30)
    g.add_argument("--interp", choices=["minterpolate", "nenhum"], default="minterpolate")

    g = ap.add_argument_group("pastas")
    g.add_argument("--pesos", type=Path, default=PESOS / "LongCat-Video")
    g.add_argument("--int8", type=Path, default=PESOS / "int8")
    g.add_argument("--recomecar", action="store_true", help="ignora o progresso salvo na --saida")
    return ap.parse_args(argv)


def opcoes(a) -> Opcoes:
    roteiro = ler_roteiro(a.roteiro, a.negativo) if a.roteiro else roteiro_de_prompt(a.prompt, a.negativo)
    if a.formato == "horizontal" and a.tamanho_final == "720x1280":
        a.tamanho_final = "1280x720"
    return Opcoes(
        pesos=a.pesos, int8=a.int8, saida=a.saida, roteiro=roteiro, duracao_s=a.duracao, formato=a.formato,
        imagem=a.imagem, modo=a.modo, passos=a.passos, cfg=a.cfg, seed=a.seed, quadros=a.quadros,
        blocos_na_gpu=a.blocos_na_gpu, reserva_gib=a.reserva_gib, pin=not a.sem_pin, atencao=a.atencao,
        ffn_tokens=a.ffn_tokens, texto_modo=a.texto, kv_cache_cpu=not a.kv_cache_gpu, vae_tiling=a.vae_tiling,
        refino=a.refino, refino_bsa=not a.refino_sem_bsa, refino_passos=a.refino_passos,
        tamanho_final=a.tamanho_final, fps_final=a.fps_final, interp=a.interp,
        max_segmentos=a.max_segmentos, recomecar=a.recomecar,
    )


def main(argv=None):
    a = argumentos(argv)
    if (a.quadros - 1) % 4:
        raise SystemExit("--quadros precisa ser 4k+1 (ex.: 33, 61, 93)")
    if a.quadros <= 13:
        raise SystemExit("--quadros precisa ser maior que os 13 de condição")
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("sem CUDA: o gerar.py só roda na GPU (python preparar.py checar)")
    Gerador(opcoes(a)).rodar()


if __name__ == "__main__":
    main()
