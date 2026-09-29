"""Produz vários projetos em sequência (áudio + imagens + montagem + capa).

Cada projeto é entregue pro `executar_projeto.py` normalmente; o que este script
acrescenta é o que faz diferença numa fila longa e sem ninguém olhando:

* **retomada**: grava o resultado de cada projeto num `--resumo` (JSON) e pula o
  que já saiu com vídeo ok numa rodada anterior — rodar de novo só refaz o que
  faltou. Pra forçar a refação de um projeto, apague a entrada dele do resumo
  **com o lote parado** (o processo em execução mantém o resumo em memória e
  reescreve o arquivo inteiro a cada projeto, então edição no meio da rodada é
  sobrescrita);
* **não desiste no primeiro erro**: projeto que falha entra no resumo como erro
  e a fila segue;
* **libera a VRAM antes de cada projeto** (`POST /free` do ComfyUI), pra etapa
  de áudio não disputar os 12GB com os pesos do Qwen ainda carregados;
* **capa opcional**: se a pasta do projeto tiver um `capa_prompt.md`, gera a capa
  com aquele prompt depois do vídeo.

Uso:
    python scripts/produzir_lote.py Projetos/ideias/bruxas_da_noite_1942 Projetos/ideias/...
    python scripts/produzir_lote.py --todos-ideias
    python scripts/produzir_lote.py --todos-ideias --resumo lote.json

A ordem da linha de comando é respeitada — importante pras séries, já que a
Parte 2 aponta pras âncoras de personagem geradas pela Parte 1. Com
`--todos-ideias`, as partes de uma mesma série saem na ordem certa porque
`_parte2` vem depois do nome base na ordenação alfabética.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW_CAPA = "comfy/image_qwen_image_2_1_t2i.json"


def liberar_vram(servidor: str) -> None:
    try:
        requests.post(f"{servidor}/free", json={"unload_models": True, "free_memory": True}, timeout=30)
    except Exception as e:  # ComfyUI fechado não é motivo pra derrubar o lote
        print(f"  (aviso: não consegui liberar a VRAM do ComfyUI: {e})", flush=True)


def rodar(comando: list[str], log_path: Path) -> int:
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(comando)}\n")
        log.flush()
        return subprocess.run(comando, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projetos", nargs="*", type=Path, help="Pastas de projeto, na ordem de produção")
    ap.add_argument("--todos-ideias", action="store_true", help="Enfileira tudo que houver em Projetos/ideias")
    ap.add_argument("--resumo", type=Path, default=Path("Projetos/_lote_resumo.json"),
                    help="JSON de progresso pra retomada (padrão: Projetos/_lote_resumo.json)")
    ap.add_argument("--logs", type=Path, default=Path("Projetos/_lote_logs"),
                    help="Pasta onde vai a saída completa de cada projeto")
    ap.add_argument("--servidor-comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--pular-capa", action="store_true", help="Não gera capa, mesmo havendo capa_prompt.md")
    args = ap.parse_args()

    projetos = list(args.projetos)
    if args.todos_ideias:
        projetos += sorted(p for p in (RAIZ / "Projetos/ideias").iterdir() if (p / "texto.md").exists())
    if not projetos:
        ap.error("informe ao menos um projeto ou use --todos-ideias")

    logs = RAIZ / args.logs
    logs.mkdir(parents=True, exist_ok=True)
    caminho_resumo = RAIZ / args.resumo
    resumo = json.loads(caminho_resumo.read_text(encoding="utf-8")) if caminho_resumo.exists() else {}

    for n, projeto in enumerate(projetos, start=1):
        projeto = Path(projeto)
        nome = projeto.name
        if resumo.get(nome, {}).get("video") == "ok":
            print(f"[{n}/{len(projetos)}] {nome}: já pronto, pulando", flush=True)
            continue

        log_path = logs / f"{nome}.log"
        inicio = time.time()
        print(f"[{n}/{len(projetos)}] {nome}: iniciando", flush=True)

        liberar_vram(args.servidor_comfy)
        codigo = rodar([sys.executable, "scripts/executar_projeto.py", str(projeto)], log_path)
        entrada = {"video": "ok" if codigo == 0 else f"erro({codigo})"}

        arquivo_capa = RAIZ / projeto / "capa_prompt.md"
        if codigo == 0 and arquivo_capa.exists() and not args.pular_capa:
            codigo_capa = rodar([
                sys.executable, "scripts/gerar_capa.py",
                str(projeto / "texto_manifesto.json"),
                "--workflow", WORKFLOW_CAPA,
                "--prompt", arquivo_capa.read_text(encoding="utf-8").strip(),
            ], log_path)
            entrada["capa"] = "ok" if codigo_capa == 0 else f"erro({codigo_capa})"

        entrada["minutos"] = round((time.time() - inicio) / 60, 1)
        resumo[nome] = entrada
        caminho_resumo.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{n}/{len(projetos)}] {nome}: {entrada}", flush=True)

    falhas = {k: v for k, v in resumo.items() if v.get("video") != "ok"}
    print("\n===== RESUMO =====", flush=True)
    for nome, dados in resumo.items():
        print(f"  {nome}: {dados}", flush=True)
    if falhas:
        print(f"\n{len(falhas)} projeto(s) com falha — a saída completa está em {logs}", flush=True)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
