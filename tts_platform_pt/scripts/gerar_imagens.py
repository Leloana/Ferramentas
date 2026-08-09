"""Gera imagens de fundo via ComfyUI (workflow Krea2 turbo), uma por FRASE do
roteiro, a partir do manifesto produzido por `gerar_video.py`.

Uso:
    python scripts/gerar_imagens.py Projetos/Video_1/historia_humanidade/texto_manifesto.json

Fluxo:
1. Lê o manifesto e pega os timestamps por frase (já calculados por
   `gerar_video.py` durante a síntese).
2. Pra cada frase, monta o prompt = texto da frase + um sufixo fixo de
   segurança (ver `_SUFIXO_SEGURANCA`) e envia pro ComfyUI local com "Refine
   Prompt" ligado, deixando o `TextGenerate` (qwen3vl) do próprio workflow
   expandir a descrição visual.
3. Baixa a imagem e salva em `<projeto>/imagens/<nome>_FF.png` (FF = frase)
   — uma imagem por frase deixa o vídeo final bem mais dinâmico do que uma
   imagem única pro vídeo inteiro.

Gera direto no formato vertical (`9:16 (Portrait Widescreen)`, formato
padrão de shorts/reels/tiktok) — sem a folga lateral que uma imagem 16:9
teria, então o movimento na montagem final (`montar_video.py`) é por zoom,
não por pan lateral.

Requer o ComfyUI Desktop aberto (API em 127.0.0.1:8188 por padrão). Como é
uma imagem por frase, o tempo total escala com o número de frases — rodar
com `--frases` pra regerar só algumas.
"""
from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import random
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
WORKFLOW_PADRAO = SCRIPT_DIR.parent / "comfy" / "image_krea2_turbo_t2i.json"
# Krea2 é o motor padrão de txt2img desta plataforma (melhor qualidade
# fotorrealista que o Z-Image-Turbo, comparado lado a lado num caso real do
# Video_10) — por isso também é o padrão pra continuidade de personagem
# (img2img), não só pra geração comum. O workflow i2i do Z-Image
# (`image_zimage_turbo_i2i.json`) continua existindo e pode ser escolhido via
# `--referencia-workflow` se for necessário no futuro.
WORKFLOW_I2I_PADRAO = SCRIPT_DIR.parent / "comfy" / "image_krea2_turbo_i2i.json"

# O modelo tende a desenhar figuras humanas nuas quando o prompt não
# menciona vestimenta, mesmo com a regra 8 do system prompt do próprio
# workflow ("assuma roupa cobrindo anatomia íntima") — na prática essa regra
# só é respeitada quando o input já fala de roupa, porque a regra 5 do mesmo
# system prompt manda não inventar detalhe de vestuário que o input não
# sustenta (testado: ligar/desligar o node de rebalanceamento de
# conditioning não resolveu sozinho, o gatilho é a ausência de vestimenta no
# prompt). Por isso declaramos vestimenta explicitamente aqui.
# Em inglês, não português: com --prompts (texto do seed em inglês) uma
# cauda em português deixava o prompt bilíngue — observado causando o
# refino (qwen3vl 4B, modelo pequeno) a "engasgar" e ecoar fragmentos
# garranchados da própria regra como texto na imagem em vez de só
# aplicá-la (ver gotcha em CLAUDE.md/GOTCHAS.md).
_SUFIXO_SEGURANCA = ", fully clothed, appropriate attire, no nudity"

# O refino de prompt (TextGenerate) segue a própria regra 4 do system prompt
# do workflow ("se o usuário pedir texto visível... coloque entre aspas")
# grande demais ao pé da letra: pra frases de narração que soam como uma
# citação fechada (terminam em ponto, tom declarativo), ele decide sozinho
# que aquilo é "texto pra mostrar na tela" e cita a frase (às vezes até
# nosso próprio sufixo de segurança) como legenda — o modelo de difusão
# então tenta desenhar essas letras e sai borrado (diffusion models são
# ruins em texto). Confirmado lendo o texto borrado: em mais de uma imagem
# ele reproduzia a frase de entrada quase literalmente. Regra extra apensada
# só na cópia que a gente envia (não mexe no workflow salvo no ComfyUI).
_REGRA_SEM_TEXTO = (
    "\n\n10. **No On-Screen Text:** The user's input is narration describing "
    "a scene, not a request for visible text. Never render the user's input "
    "(or any paraphrase, translation, or quote of it) as visible text, "
    "caption, subtitle, or typography in the image, even partially — unless "
    "it explicitly describes a sign, label, or document with specific words "
    "to display."
)

# Prompt refinado grande (parágrafo longo, com vários detalhes simultâneos)
# aumenta a taxa de alucinação do modelo especificamente em formatos
# verticais/retrato (9:16, 3:4 — os usados pra celular) — observado
# comparando gerações do mesmo tipo de frase em formatos diferentes. Regra
# extra apensada (mesmo mecanismo de _REGRA_SEM_TEXTO) pedindo um prompt
# final curto em vez do parágrafo rico que a regra 2 do system prompt
# original incentiva por padrão.
_REGRA_PROMPT_CURTO = (
    "\n\n11. **Keep It Short:** Output a concise prompt of at most 40 words "
    "— a single short sentence or two, not a richly layered paragraph. "
    "Long, densely detailed prompts cause this model to hallucinate "
    "(duplicated panels, rotated framing, extra limbs), especially in "
    "vertical/portrait aspect ratios. Prefer fewer, clearer details over "
    "exhaustive description."
)

_NODE_PROMPT = "30:19"
_NODE_REFINAR = "30:24"
_NODE_SISTEMA_REFINO = "30:18"
_NODE_SAMPLER = "30:3"
_NODE_RESOLUCAO = "49"
_NODE_SAVE = "29"

# Nós do workflow alternativo `image_zimage_turbo_t2i.json` (Z-Image-Turbo,
# ver comfy/GOTCHAS.md item 8 — trocado pra evitar o desvio pra anime do
# krea2_turbo). Esse workflow não tem passo de refino (o CLIPTextEncode do
# Z-Image não é multimodal/LLM como o qwen3vl_4b do krea2, então não dá pra
# reaproveitar o node TextGenerate) — o texto vai direto pro CLIPTextEncode,
# o que é seguro aqui porque `--prompts` já pede pra escrever a cena concreta
# à mão (ver texto_prompts.json em CLAUDE.md), não a frase abstrata da
# narração.
_ZIMAGE_NODE_PROMPT = "5"
_ZIMAGE_NODE_RESOLUCAO = "7"
_ZIMAGE_NODE_SAMPLER = "9"
_ZIMAGE_NODE_SAVE = "11"

# Nós extras do workflow `image_zimage_turbo_i2i.json` (continuidade de
# personagem via img2img, ver plano_continuidade_personagem.md) — carrega a
# imagem de referência já enviada ao ComfyUI e redimensiona pro aspect_ratio
# pedido antes de virar o latent inicial do KSampler (que nesse workflow usa
# denoise<1 em vez do denoise=1 do t2i puro).
_ZIMAGE_NODE_REF_IMAGEM = "12"

# Nó extra equivalente no workflow `image_krea2_turbo_i2i.json` (mesmo
# mecanismo acima, cabeado em cima do grafo Krea2 em vez do Z-Image — ver
# `_NODE_SAMPLER`/`_NODE_RESOLUCAO` acima pros nós que esse workflow
# compartilha com `image_krea2_turbo_t2i.json`). `LoadImage` (`30:60`) →
# `ImageScale` (`30:61`, `crop=center`) → `VAEEncode` (`30:62`) alimentando
# o `latent_image` do `KSampler` (`30:3`) no lugar do `EmptyLatentImage`
# (`30:5`, que fica órfão no grafo mas não custa nada — ComfyUI só executa
# nós alcançáveis a partir do `SaveImage`).
_KREA2_NODE_REF_IMAGEM = "30:60"


def montar_prompt(texto: str) -> str:
    return texto.strip() + _SUFIXO_SEGURANCA


def enviar_imagem_referencia(server: str, caminho: Path) -> str:
    """Envia uma imagem de referência local pro ComfyUI e retorna o
    identificador pronto pra LoadImage.inputs.image. Usa sempre o
    name/subfolder da resposta do /upload/image (que já faz dedup por hash),
    não o nome do arquivo local."""
    mimetype = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    resp = requests.post(
        f"{server}/upload/image",
        files={"image": (caminho.name, caminho.read_bytes(), mimetype)},
        timeout=60,
    )
    resp.raise_for_status()
    info = resp.json()
    subfolder = info.get("subfolder", "")
    return f"{subfolder}/{info['name']}" if subfolder else info["name"]


def gerar_imagem(
    server: str,
    workflow: dict,
    texto: str,
    aspect_ratio: str,
    destino: Path,
    timeout_s: float = 600,
    referencia_imagem: str | None = None,
    referencia_denoise: float = 0.5,
) -> dict:
    wf = copy.deepcopy(workflow)
    prompt_final = montar_prompt(texto)
    eh_krea2 = _NODE_REFINAR in wf
    if eh_krea2:
        wf[_NODE_PROMPT]["inputs"]["value"] = prompt_final
        wf[_NODE_REFINAR]["inputs"]["value"] = True
        wf[_NODE_SISTEMA_REFINO]["inputs"]["value"] += _REGRA_SEM_TEXTO + _REGRA_PROMPT_CURTO
        wf[_NODE_RESOLUCAO]["inputs"]["aspect_ratio"] = aspect_ratio
        wf[_NODE_SAMPLER]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
        if referencia_imagem:
            wf[_NODE_SAMPLER]["inputs"]["denoise"] = referencia_denoise
            wf[_KREA2_NODE_REF_IMAGEM]["inputs"]["image"] = referencia_imagem
        node_save = _NODE_SAVE
    elif referencia_imagem:
        wf[_ZIMAGE_NODE_PROMPT]["inputs"]["text"] = prompt_final
        wf[_ZIMAGE_NODE_RESOLUCAO]["inputs"]["aspect_ratio"] = aspect_ratio
        wf[_ZIMAGE_NODE_SAMPLER]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
        wf[_ZIMAGE_NODE_SAMPLER]["inputs"]["denoise"] = referencia_denoise
        wf[_ZIMAGE_NODE_REF_IMAGEM]["inputs"]["image"] = referencia_imagem
        node_save = _ZIMAGE_NODE_SAVE
    else:
        wf[_ZIMAGE_NODE_PROMPT]["inputs"]["text"] = prompt_final
        wf[_ZIMAGE_NODE_RESOLUCAO]["inputs"]["aspect_ratio"] = aspect_ratio
        wf[_ZIMAGE_NODE_SAMPLER]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
        node_save = _ZIMAGE_NODE_SAVE

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
        if entrada:
            status = entrada.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI falhou ao gerar a imagem (prompt_id={prompt_id}): {status.get('messages')}")
            if status.get("completed"):
                break
        time.sleep(2)
    else:
        raise TimeoutError(f"ComfyUI não terminou a imagem em {timeout_s}s (prompt_id={prompt_id})")

    imagem = entrada["outputs"][node_save]["images"][0]
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
    return {"prompt_final": prompt_final, "arquivo_comfy": imagem["filename"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifesto", type=Path, help="Caminho do <nome>_manifesto.json gerado por gerar_video.py")
    ap.add_argument("--frases", default=None,
                     help='Regera só essas frases (1-based, separadas por vírgula, ex.: "1,2,5"). Padrão: todas.')
    ap.add_argument("--prompts", type=Path, default=None, help=(
        'JSON {"<frase>": "descrição visual reescrita"} pra usar como prompt em vez do '
        "texto literal da narração daquela frase (recomendado: o texto da narração costuma "
        "ser abstrato demais pra visualizar direto — reescrever numa cena concreta dá "
        "imagem melhor). Frases sem entrada no arquivo caem no texto literal."
    ))
    ap.add_argument("--workflow", type=Path, default=WORKFLOW_PADRAO)
    ap.add_argument("--aspect-ratio", default="9:16 (Portrait Widescreen)", help="Formato do ResolutionSelector do workflow")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--referencia", type=Path, default=None, help=(
        'JSON {"<frase>": "<caminho da imagem de referência>"} pra gerar aquela frase via '
        "img2img (denoise parcial) em cima da imagem indicada, em vez de txt2img puro — "
        "mecanismo opcional de continuidade de personagem entre frases (ver "
        "plano_continuidade_personagem.md). Frases sem entrada no arquivo caem no txt2img normal."
    ))
    ap.add_argument("--referencia-denoise", type=float, default=0.5, help=(
        "Denoise do img2img pras frases com --referencia (0-1, quanto menor mais fiel à "
        "imagem de referência). Só tem efeito se --referencia for passado."
    ))
    ap.add_argument("--referencia-workflow", type=Path, default=WORKFLOW_I2I_PADRAO, help=(
        "Workflow do ComfyUI usado pras frases com --referencia. Só é lido do disco se "
        "--referencia for passado."
    ))
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

    if "frases" not in manifesto:
        raise SystemExit(
            "O manifesto não tem timestamps por frase "
            "(rode gerar_video.py de novo pra regerar com a versão atual do motor)."
        )

    indices_frases = None
    if args.frases:
        indices_frases = {int(x) for x in args.frases.split(",")}

    prompts_custom = {}
    if args.prompts:
        if not args.prompts.exists():
            raise SystemExit(f"Arquivo de prompts não encontrado: {args.prompts}")
        prompts_custom = {int(k): v for k, v in json.loads(args.prompts.read_text(encoding="utf-8")).items()}

    referencias = {}
    workflow_i2i = None
    if args.referencia:
        if not args.referencia.exists():
            raise SystemExit(f"Arquivo de referências não encontrado: {args.referencia}")
        if not args.referencia_workflow.exists():
            raise SystemExit(f"Workflow i2i do ComfyUI não encontrado: {args.referencia_workflow}")
        referencias_raw = {int(k): v for k, v in json.loads(args.referencia.read_text(encoding="utf-8")).items()}
        for j, caminho in referencias_raw.items():
            caminho = Path(caminho)
            if not caminho.exists():
                raise SystemExit(f"Imagem de referência da frase {j} não encontrada: {caminho}")
            referencias[j] = caminho
        workflow_i2i = json.loads(args.referencia_workflow.read_text(encoding="utf-8"))

    tarefas = [
        (j, prompts_custom.get(j, frase["texto"]))
        for j, frase in enumerate(manifesto["frases"], start=1)
        if indices_frases is None or j in indices_frases
    ]

    sobras_referencia = set(referencias) - {j for j, _ in tarefas}
    if sobras_referencia:
        print(f"Aviso: --referencia tem frase(s) fora desta execução, ignorada(s): {sorted(sobras_referencia)}")

    print(f"Gerando {len(tarefas)} imagem(ns) de fundo (uma por frase) em {dir_imagens}...")
    resultado = []
    cache_upload = {}
    try:
        for n, (j, texto) in enumerate(tarefas, start=1):
            destino = dir_imagens / f"{nome_base}_{j:02d}.png"
            print(f"  [{n}/{len(tarefas)}] frase {j} -> {destino.name}")
            caminho_ref = referencias.get(j)
            if caminho_ref is None:
                info = gerar_imagem(args.server, workflow, texto, args.aspect_ratio, destino)
                resultado.append({"frase": j, "arquivo": destino.name, **info})
            else:
                if caminho_ref not in cache_upload:
                    cache_upload[caminho_ref] = enviar_imagem_referencia(args.server, caminho_ref)
                info = gerar_imagem(
                    args.server, workflow_i2i, texto, args.aspect_ratio, destino,
                    referencia_imagem=cache_upload[caminho_ref], referencia_denoise=args.referencia_denoise,
                )
                resultado.append({
                    "frase": j, "arquivo": destino.name, **info,
                    "referencia": str(caminho_ref), "referencia_denoise": args.referencia_denoise,
                })
            print(f"      prompt: {info['prompt_final'][:100]}...")
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(f"Não consegui falar com o ComfyUI em {args.server}. Ele está aberto?") from e

    # Mescla com o manifesto de imagens existente em vez de sobrescrever —
    # rodar com --frases pra regerar só algumas não pode apagar o registro
    # das outras que já estavam boas.
    caminho_manifesto_img = projeto / f"{nome_base}_imagens_manifesto.json"
    existentes = json.loads(caminho_manifesto_img.read_text(encoding="utf-8")) if caminho_manifesto_img.exists() else []
    por_chave = {e["frase"]: e for e in existentes}
    for novo in resultado:
        por_chave[novo["frase"]] = novo
    final = [por_chave[k] for k in sorted(por_chave)]
    caminho_manifesto_img.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifesto de imagens salvo em {caminho_manifesto_img}")


if __name__ == "__main__":
    main()
