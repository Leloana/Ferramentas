"""Escada de testes para rodar quando a GPU estiver livre (RTX 4070 12 GB).

Cada etapa roda o gerar.py num processo novo (memória limpa), com saída em
trabalho/teste_gpu/<etapa>/, e no fim escreve trabalho/teste_gpu/RESULTADOS.md
com tempo, pico de VRAM e RAM livre mínima de cada uma. Uma etapa que falha
não impede as seguintes de rodarem (use --parar-no-erro para parar).

    python teste_gpu.py                 # todas, em ordem
    python teste_gpu.py --so curto      # uma só
    python teste_gpu.py --ate continuacao
    python teste_gpu.py --listar

Ordem pensada para achar o problema cedo e barato: primeiro um clipe de 2 s,
depois um segmento cheio, depois a continuação (KV cache), depois 16 s, o
refino, e só no fim os 90 s (horas).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TRAB = AQUI / "trabalho" / "teste_gpu"
PROMPT = ("realistic filming style, vertical video, a young woman in a yellow raincoat walks a golden retriever "
          "along a wet city sidewalk at dusk, neon reflections on the ground, the camera follows from the front, "
          "handheld, natural motion")

ETAPAS = [
    ("checar", "ambiente, pesos e INT8", None),
    ("curto", "1 segmento de 33 quadros (2,2 s): carrega, gera, decodifica",
     ["--quadros", "33", "--duracao", "2", "--max-segmentos", "1"]),
    ("segmento", "1 segmento cheio de 93 quadros (6,2 s)",
     ["--duracao", "6", "--max-segmentos", "1"]),
    ("continuacao", "2 segmentos: testa generate_vc + KV cache na RAM",
     ["--duracao", "11", "--max-segmentos", "2"]),
    ("blocos0", "mesmo do segmento com 0 blocos fixos: piso de VRAM e custo do offload",
     ["--duracao", "6", "--max-segmentos", "1", "--blocos-na-gpu", "0"]),
    ("16s", "3 segmentos + pós (minterpolate 30 fps, 720x1280)",
     ["--duracao", "16"]),
    ("refino_espacial", "refino oficial só espacial em 1 segmento (experimental)",
     ["--duracao", "6", "--max-segmentos", "1", "--refino", "espacial"]),
    ("90s", "o alvo: 90 s vertical (17 segmentos, horas)",
     ["--duracao", "90"]),
]


def resumir(pasta: Path) -> dict:
    med = pasta / "medicoes.jsonl"
    if not med.exists():
        return {}
    linhas = [json.loads(l) for l in med.read_text(encoding="utf-8").splitlines() if l.strip()]
    segs = [l for l in linhas if l.get("etapa") in ("estagio1",) or str(l.get("etapa", "")).startswith("refino_")]
    return {
        "pico_vram_gib": max((l.get("vram_pico_gib", 0) for l in linhas), default=None),
        "ram_livre_min_gib": min((l.get("ram_livre_gib", 1e9) for l in linhas), default=None),
        "min_por_segmento": [round(l["segundos"] / 60, 1) for l in segs],
        "blocos_na_gpu": next((l.get("blocos_na_gpu") for l in linhas if "blocos_na_gpu" in l), None),
        "atencao": next((l.get("atencao") for l in linhas if "atencao" in l), None),
    }


def rodar(nome, args, extra) -> dict:
    pasta = TRAB / nome
    t0 = time.time()
    if args is None:
        cmd = [sys.executable, str(AQUI / "preparar.py"), "checar"]
    else:
        cmd = [sys.executable, str(AQUI / "gerar.py"), "--prompt", PROMPT, "--saida", str(pasta), "--recomecar", *args, *extra]
    print(f"\n=== {nome}: {' '.join(cmd[1:])}", flush=True)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "medicoes.jsonl").unlink(missing_ok=True)  # medição limpa a cada rodada
    with (pasta / "log.txt").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=AQUI)
        cauda = []
        for linha in proc.stdout:
            print(linha, end="", flush=True)
            log.write(linha)
            cauda = (cauda + [linha.rstrip()])[-15:]
        rc = proc.wait()
    oom = any("out of memory" in l.lower() for l in cauda)
    return {"etapa": nome, "ok": rc == 0, "rc": rc, "oom": oom, "minutos": round((time.time() - t0) / 60, 1),
            **resumir(pasta), "cauda": cauda[-5:] if rc else []}


def escrever_md(resultados):
    linhas = ["# Resultados do teste na GPU", "", f"Gerado em {time.strftime('%Y-%m-%d %H:%M')}.", "",
              "| etapa | ok | min total | min/segmento | pico VRAM GiB | RAM livre mín GiB | blocos GPU | atenção |",
              "|---|---|---|---|---|---|---|---|"]
    for r in resultados:
        linhas.append(f"| {r['etapa']} | {'sim' if r['ok'] else ('OOM' if r['oom'] else 'não')} | {r['minutos']} | "
                      f"{r.get('min_por_segmento', '')} | {r.get('pico_vram_gib', '')} | {r.get('ram_livre_min_gib', '')} | "
                      f"{r.get('blocos_na_gpu', '')} | {r.get('atencao', '')} |")
    for r in resultados:
        if not r["ok"] and r.get("cauda"):
            linhas += ["", f"## {r['etapa']} falhou", "", "```", *r["cauda"], "```"]
    (TRAB / "RESULTADOS.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (TRAB / "resultados.json").write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--so", action="append", help="roda só esta etapa (pode repetir)")
    ap.add_argument("--ate", help="roda até esta etapa, inclusive")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--parar-no-erro", action="store_true")
    ap.add_argument("extra", nargs="*", help="repassado ao gerar.py depois de --, ex.: -- --atencao flash2")
    a = ap.parse_args()
    if a.listar:
        for n, d, _ in ETAPAS:
            print(f"{n:16s} {d}")
        return
    nomes = [n for n, _, _ in ETAPAS]
    escolha = nomes
    if a.so:
        escolha = [n for n in nomes if n in a.so]
    elif a.ate:
        escolha = nomes[: nomes.index(a.ate) + 1]
    TRAB.mkdir(parents=True, exist_ok=True)
    resultados = []
    for n, _, args in ETAPAS:
        if n not in escolha:
            continue
        r = rodar(n, args, a.extra)
        resultados.append(r)
        escrever_md(resultados)
        if not r["ok"] and (a.parar_no_erro or n == "checar"):
            break
    print(f"\nresumo em {TRAB / 'RESULTADOS.md'}")


if __name__ == "__main__":
    main()
