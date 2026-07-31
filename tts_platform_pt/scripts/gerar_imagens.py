"""Gera imagens de fundo via ComfyUI (workflow Krea2 turbo), uma por parte do
roteiro, a partir do manifesto produzido por `gerar_video.py`.

Uso:
    python scripts/gerar_imagens.py Projetos/video-curto/humanidade_manifesto.json

Fluxo:
1. Lê o manifesto e pega o texto de cada parte curta (os mesmos blocos
   agrupados por frase que já viraram áudio em `gerar_video.py`).
2. Pra cada parte, monta o prompt = texto original + um sufixo fixo de
   segurança (ver `_SUFIXO_SEGURANCA`) e envia pro ComfyUI local com "Refine
   Prompt" ligado, deixando o `TextGenerate` (qwen3vl) do próprio workflow
   expandir a descrição visual.
3. Baixa a imagem e salva em `<projeto>/imagens/<nome>_NN.png`, na mesma
   numeração de `<projeto>/video-curto/<nome>_NN.wav`.

Requer o ComfyUI Desktop aberto (API em 127.0.0.1:8188 por padrão).
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
WORKFLOW_PADRAO = SCRIPT_DIR.parent / "comfy" / "image_krea2_turbo_t2i.json"

# O modelo tende a desenhar figuras humanas nuas quando o prompt não
# menciona vestimenta, mesmo com a regra 8 do system prompt do próprio
# workflow ("assuma roupa cobrindo anatomia íntima") — na prática essa regra
# só é respeitada quando o input já fala de roupa, porque a regra 5 do mesmo
# system prompt manda não inventar detalhe de vestuário que o input não
# sustenta (testado: ligar/desligar o node de rebalanceamento de
# conditioning não resolveu sozinho, o gatilho é a ausência de vestimenta no
# prompt). Por isso declaramos vestimenta explicitamente aqui.
_SUFIXO_SEGURANCA = (
    ", todas as pessoas retratadas devem estar completamente vestidas com "
    "roupas apropriadas ao contexto e à época da cena, sem nudez"
)

_NODE_PROMPT = "30:19"
_NODE_REFINAR = "30:24"
_NODE_SAMPLER = "30:3"
_NODE_RESOLUCAO = "49"
_NODE_SAVE = "29"


def montar_prompt(texto: str) -> str:
    return texto.strip() + _SUFIXO_SEGURANCA


def gerar_imagem(
    server: str, workflow: dict, texto: str, aspect_ratio: str, destino: Path, timeout_s: float = 600
) -> dict:
    wf = copy.deepcopy(workflow)
    wf[_NODE_PROMPT]["inputs"]["value"] = montar_prompt(texto)
    wf[_NODE_REFINAR]["inputs"]["value"] = True
    wf[_NODE_RESOLUCAO]["inputs"]["aspect_ratio"] = aspect_ratio
    wf[_NODE_SAMPLER]["inputs"]["seed"] = random.randint(0, 2**32 - 1)

    resp = requests.post(f"{server}/prompt", json={"prompt": wf}, timeout=30)
    resp.raise_for_status()
    dados = resp.json()
    if dados.get("node_errors"):
        raise RuntimeError(f"ComfyUI recusou o workflow: {dados['node_errors']}")
    prompt_id = dados["prompt_id"]

    inicio = time.monotonic()
    entrada = None
    while time.monotonic() - inicio < timeout_s:
        hist = requests.get(f"{server}/history/{prompt_id}", timeout=30).json()
        entrada = hist.get(prompt_id)
        if entrada and entrada.get("status", {}).get("completed"):
            break
        time.sleep(2)
    else:
        raise TimeoutError(f"ComfyUI não terminou a imagem em {timeout_s}s (prompt_id={prompt_id})")

    imagem = entrada["outputs"][_NODE_SAVE]["images"][0]
    resp_img = requests.get(
        f"{server}/view",
        params={
            "filename": imagem["filename"],
            "subfolder": imagem.get("subfolder", ""),
            "type": imagem.get("type", "output"),
        },
        timeout=60,
    )
    resp_img.raise_for_status()
    destino.write_bytes(resp_img.content)
    return {"prompt_final": wf[_NODE_PROMPT]["inputs"]["value"], "arquivo_comfy": imagem["filename"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifesto", type=Path, help="Caminho do <nome>_manifesto.json gerado por gerar_video.py")
    ap.add_argument("--workflow", type=Path, default=WORKFLOW_PADRAO)
    ap.add_argument("--aspect-ratio", default="16:9 (Widescreen)")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    args = ap.parse_args()

    if not args.manifesto.exists():
        raise SystemExit(f"Manifesto não encontrado: {args.manifesto}")
    if not args.workflow.exists():
        raise SystemExit(f"Workflow do ComfyUI não encontrado: {args.workflow}")

    manifesto = json.loads(args.manifesto.read_text(encoding="utf-8"))
    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))

    projeto = args.manifesto.parent
    nome_base = Path(manifesto["roteiro"]).stem
    dir_imagens = projeto / "imagens"
    dir_imagens.mkdir(parents=True, exist_ok=True)

    partes = manifesto["video_curto"]
    print(f"Gerando {len(partes)} imagem(ns) de fundo em {dir_imagens}...")
    resultado = []
    try:
        for i, parte in enumerate(partes, start=1):
            destino = dir_imagens / f"{nome_base}_{i:02d}.png"
            print(f"  [{i}/{len(partes)}] {parte['arquivo']} -> {destino.name}")
            info = gerar_imagem(args.server, workflow, parte["texto"], args.aspect_ratio, destino)
            print(f"      prompt: {info['prompt_final'][:100]}...")
            resultado.append({"arquivo": destino.name, **info})
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(f"Não consegui falar com o ComfyUI em {args.server}. Ele está aberto?") from e

    caminho_manifesto_img = projeto / f"{nome_base}_imagens_manifesto.json"
    caminho_manifesto_img.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifesto de imagens salvo em {caminho_manifesto_img}")


if __name__ == "__main__":
    main()
