"""Gerador de video local via ComfyUI + Sulphur-2 (LTX-2.3).

Pre-requisito: o ComfyUI Desktop precisa estar aberto (API HTTP ativa) e os
modelos precisam ter sido baixados antes com `python setup_models.py`.

Exemplos:
    python gerar_video.py --prompt "um gato astronauta flutuando no espaco"
    python gerar_video.py --modo i2v --imagem foto.png --prompt "a cena ganha vida, camera lenta"
    python gerar_video.py --qualidade --prompt "mesmo prompt, mais nitido e bem mais lento"
"""
import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).parent / "workflows"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_COMFYUI_OUTPUT = (
    Path.home() / "AppData" / "Local" / "Comfy-Desktop" / "ComfyUI-Shared" / "output"
)
NEGATIVO_PADRAO = (
    "pc game, console game, video game, cartoon, childish, ugly, "
    "voiceover, narration, narrator reading, spoken text, person talking, speech, subtitles"
)
# Negativo oficial do Wan (em chines, como o modelo foi treinado). Com os LoRAs
# de 4 passos o CFG fica em 1 e ele quase nao pesa, mas nao atrapalha.
NEGATIVO_WAN = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，"
    "JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
    "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)


def arredondar_32(valor: int) -> int:
    return max(32, (valor // 32) * 32)


def chamar_api(host: str, caminho: str, dados: dict | None = None, metodo: str = "GET"):
    url = f"http://{host}{caminho}"
    corpo = json.dumps(dados).encode("utf-8") if dados is not None else None
    req = urllib.request.Request(url, data=corpo, method=metodo)
    if corpo is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            conteudo = resp.read()
            return json.loads(conteudo) if conteudo.strip() else {}  # /free responde vazio
    except urllib.error.HTTPError as e:
        # ComfyUI respondeu (servidor no ar), mas rejeitou o pedido - o corpo
        # traz o motivo (ex.: workflow invalido, modelo faltando).
        return json.loads(e.read())
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Nao foi possivel falar com o ComfyUI em http://{host}. "
            "Abra o ComfyUI Desktop e tente novamente."
        ) from e


def enviar_imagem(host: str, caminho_imagem: Path) -> str:
    import mimetypes

    boundary = uuid.uuid4().hex
    tipo, _ = mimetypes.guess_type(caminho_imagem.name)
    tipo = tipo or "application/octet-stream"
    conteudo = caminho_imagem.read_bytes()

    corpo = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{caminho_imagem.name}"\r\n'
        f"Content-Type: {tipo}\r\n\r\n"
    ).encode("utf-8") + conteudo + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"http://{host}/upload/image",
        data=corpo,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            info = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Nao foi possivel enviar a imagem para o ComfyUI em http://{host}."
        ) from e

    if info.get("subfolder"):
        return f"{info['subfolder']}/{info['name']}"
    return info["name"]


def dimensoes_wan(imagem: Path, max_lado: int, multiplo: int = 16) -> tuple[int, int]:
    """Mantem a proporcao da imagem, lado maior = max_lado, multiplos de `multiplo`."""
    from PIL import Image

    with Image.open(imagem) as img:
        w, h = img.size
    escala = max_lado / max(w, h)
    m = multiplo
    return max(m, round(w * escala / m) * m), max(m, round(h * escala / m) * m)


LADO_BASE_WAN = 832  # acima disso o 14B com 81 quadros treme; o hi-res fix gera o movimento aqui


def montar_workflow_wan22(args) -> dict:
    # Hi-res fix: o 14B direto em 720p x 81 quadros sai com a camera tremendo
    # (medido em 2026-10-14). Entao o movimento e gerado em 832 e o modelo low
    # noise so refina em alta resolucao (re-ruido a partir do passo 2 de 4).
    hires = args.max_lado > LADO_BASE_WAN and not args.nativo
    nome = "wan22_i2v_hires.json" if hires else "wan22_i2v.json"
    workflow = json.loads((WORKFLOWS_DIR / nome).read_text(encoding="utf-8"))
    largura, altura = dimensoes_wan(args.imagem, LADO_BASE_WAN if hires else args.max_lado)
    # Wan gera 4k+1 frames
    frames = (max(args.frames, 5) - 1) // 4 * 4 + 1
    seed = args.seed if args.seed is not None else random.randint(0, 2**48)

    workflow["8"]["inputs"]["text"] = args.prompt
    workflow["9"]["inputs"]["text"] = args.negativo or NEGATIVO_WAN
    workflow["11"]["inputs"]["image"] = enviar_imagem(args.host, args.imagem)
    workflow["12"]["inputs"].update(width=largura, height=altura, length=frames)
    workflow["13"]["inputs"]["noise_seed"] = seed
    workflow["16"]["inputs"]["fps"] = args.fps
    descricao = f"{largura}x{altura}"
    if hires:
        final_l, final_a = dimensoes_wan(args.imagem, args.max_lado)
        workflow["20"]["inputs"].update(width=final_l, height=final_a)
        workflow["22"]["inputs"].update(width=final_l, height=final_a, length=frames)
        workflow["23"]["inputs"]["noise_seed"] = seed + 1
        descricao += f" -> refino em {final_l}x{final_a}"
    print(f"Wan 2.2 14B: {descricao}, {frames} frames a {args.fps} fps (~{frames / args.fps:.1f}s)")
    return workflow


def montar_workflow_wan22_5b(args) -> dict:
    """Wan 2.2 5B (TI2V): feito para 720p nativo (1280x704) a 24fps e cabe nos 12GB."""
    workflow = json.loads((WORKFLOWS_DIR / "wan22_5b_i2v.json").read_text(encoding="utf-8"))
    largura, altura = dimensoes_wan(args.imagem, args.max_lado, multiplo=32)
    frames = (max(args.frames, 5) - 1) // 4 * 4 + 1

    workflow["8"]["inputs"]["text"] = args.prompt
    workflow["9"]["inputs"]["text"] = args.negativo or NEGATIVO_WAN
    workflow["11"]["inputs"]["image"] = enviar_imagem(args.host, args.imagem)
    workflow["12"]["inputs"].update(width=largura, height=altura, length=frames)
    workflow["13"]["inputs"]["seed"] = args.seed if args.seed is not None else random.randint(0, 2**48)
    workflow["13"]["inputs"]["steps"] = args.passos or 20
    workflow["16"]["inputs"]["fps"] = args.fps
    print(f"Wan 2.2 5B: {largura}x{altura}, {frames} frames a {args.fps} fps (~{frames / args.fps:.1f}s)")
    return workflow


def montar_workflow_upscale(host: str, video: Path, largura: int, altura: int) -> dict:
    """Segunda passada: 4x-UltraSharp quadro a quadro e reduz para largura x altura."""
    workflow = json.loads((WORKFLOWS_DIR / "upscale_video.json").read_text(encoding="utf-8"))
    workflow["1"]["inputs"]["file"] = enviar_imagem(host, video)
    workflow["5"]["inputs"].update(width=largura, height=altura)
    return workflow


def montar_workflow_interpolar(host: str, video: Path, multiplicador: int, fps: float) -> dict:
    """RIFE 4.9: cria (multiplicador-1) quadros entre cada par; fps final = fps * multiplicador."""
    workflow = json.loads((WORKFLOWS_DIR / "interpolar_video.json").read_text(encoding="utf-8"))
    workflow["1"]["inputs"]["file"] = enviar_imagem(host, video)
    workflow["3"]["inputs"]["multiplier"] = multiplicador
    workflow["6"]["inputs"]["fps"] = fps * multiplicador
    return workflow


def fps_do_video(video: Path, padrao: float) -> float:
    import subprocess

    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        num, den = saida.split("/")
        return float(num) / float(den)
    except (OSError, ValueError, ZeroDivisionError, subprocess.SubprocessError):
        return padrao


CRF_INTERMEDIARIO = 10  # quando ainda vai passar por upscale/interpolacao: evita comprimir duas vezes


def definir_crf(workflow: dict, crf: float) -> dict:
    """O SaveVideo do ComfyUI usa CRF 23 por padrao: ~2,4 Mbps em 720p, borra
    detalhe fino (pior ainda depois da interpolacao, com o dobro de quadros)."""
    for no in workflow.values():
        if no["class_type"] == "SaveVideo" and no["inputs"].get("format.codec") == "h264":
            no["inputs"].update({"format.codec.encoding": "re-encode", "format.codec.encoding.crf": float(crf)})
    return workflow


def executar(host: str, workflow: dict, timeout_min: int) -> tuple[str, str]:
    """Envia o workflow, espera terminar e devolve (arquivo, subpasta) do video gerado."""
    resposta = chamar_api(host, "/prompt", {"prompt": workflow, "client_id": str(uuid.uuid4())}, metodo="POST")

    if "error" in resposta:
        print("[erro] ComfyUI rejeitou o workflow:")
        print(json.dumps(resposta["error"], indent=2, ensure_ascii=False))
        node_errors = resposta.get("node_errors", {})
        if node_errors:
            print("\nDetalhes por no:")
            print(json.dumps(node_errors, indent=2, ensure_ascii=False))
        print(
            "\nSe o erro mencionar um arquivo de modelo faltando, rode "
            "`python setup_models.py` primeiro."
        )
        sys.exit(1)

    entrada = aguardar_conclusao(host, resposta["prompt_id"], timeout_min)
    return extrair_video(entrada)


def montar_workflow(args) -> dict:
    if args.modelo == "wan22":
        return montar_workflow_wan22(args)
    if args.modelo == "wan22-5b":
        return montar_workflow_wan22_5b(args)
    sufixo = "qualidade" if args.qualidade else "distilled"
    nome_arquivo = f"{args.modo}_{sufixo}.json"
    workflow = json.loads((WORKFLOWS_DIR / nome_arquivo).read_text(encoding="utf-8"))

    workflow["29"]["inputs"]["value"] = args.prompt
    workflow["41"]["inputs"]["text"] = args.negativo or NEGATIVO_PADRAO
    workflow["27"]["inputs"]["value"] = args.frames
    workflow["26"]["inputs"]["value"] = args.fps

    seed_base = args.seed if args.seed is not None else random.randint(0, 2**48)
    seed_refine = args.seed + 1 if args.seed is not None else random.randint(0, 2**48)
    workflow["2"]["inputs"]["noise_seed"] = seed_base
    workflow["1"]["inputs"]["noise_seed"] = seed_refine

    if args.modo == "i2v":
        nome_upload = enviar_imagem(args.host, args.imagem)
        workflow["67"]["inputs"]["image"] = nome_upload
        workflow["68"]["inputs"]["largest_size"] = args.max_lado
    else:
        largura_base = arredondar_32(args.largura // 2)
        altura_base = arredondar_32(args.altura // 2)
        workflow["21"]["inputs"]["width"] = largura_base
        workflow["21"]["inputs"]["height"] = altura_base
        workflow["21"]["inputs"]["length"] = args.frames

    return workflow


def aguardar_conclusao(host: str, prompt_id: str, timeout_min: int) -> dict:
    print("Gerando video... (isso pode levar varios minutos nessa GPU)")
    inicio = time.time()
    while time.time() - inicio < timeout_min * 60:
        historico = chamar_api(host, f"/history/{prompt_id}")
        if prompt_id in historico:
            entrada = historico[prompt_id]
            status = entrada.get("status", {})
            if status.get("completed"):
                return entrada
            if status.get("status_str") == "error":
                erros = [
                    f"{m[1].get('node_type')}: {m[1].get('exception_message', '').strip()[:500]}"
                    for m in status.get("messages", [])
                    if m[0] == "execution_error"
                ]
                raise RuntimeError(f"ComfyUI reportou erro na geracao: {'; '.join(erros) or status}")
        time.sleep(3)
    raise TimeoutError(f"Geracao nao terminou em {timeout_min} minutos.")


def extrair_video(entrada_historico: dict) -> tuple[str, str]:
    for saida in entrada_historico.get("outputs", {}).values():
        for chave in ("videos", "images", "gifs"):
            # LoadVideo tambem aparece nas saidas, com type "input"
            for item in saida.get(chave) or []:
                if item.get("type", "output") == "output":
                    return item["filename"], item.get("subfolder", "")
    raise RuntimeError("Nenhum arquivo de video encontrado na saida do ComfyUI.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompt", help="Descricao do video a gerar (obrigatorio, exceto com --video)")
    parser.add_argument(
        "--video",
        type=Path,
        help="Nao gera nada: so aplica --upscale/--interpolar num video que ja existe",
    )
    parser.add_argument(
        "--modelo",
        choices=["wan22", "wan22-5b", "ltx"],
        default="wan22",
        help="wan22 (padrao, Wan 2.2 14B imagem->video), wan22-5b (720p nativo) ou ltx (Sulphur-2, descontinuado)",
    )
    parser.add_argument("--modo", choices=["t2v", "i2v"], default="t2v", help="Somente --modelo ltx")
    parser.add_argument(
        "--qualidade",
        action="store_true",
        help="Usa a receita de sampling completa (CFG real + 50 passos na primeira fase) em vez da distilled. Mais nitido, bem mais lento.",
    )
    parser.add_argument("--imagem", type=Path, help="Imagem inicial (obrigatorio para --modo i2v)")
    parser.add_argument("--negativo", default=None, help="Prompt negativo (padrao interno se omitido)")
    parser.add_argument("--frames", type=int, default=None, help="Numero de frames (padrao: wan22 81 = 5s a 16fps; ltx 241 = 10s a 24fps)")
    parser.add_argument("--fps", type=int, default=None, help="Padrao: wan22 16, ltx 24")
    parser.add_argument("--largura", type=int, default=768, help="Somente --modo t2v")
    parser.add_argument("--altura", type=int, default=512, help="Somente --modo t2v")
    parser.add_argument("--max-lado", type=int, default=None, dest="max_lado", help="Imagem->video: lado maior do video (padrao: wan22 832, ltx 1024)")
    parser.add_argument(
        "--nativo",
        action="store_true",
        help="wan22 com --max-lado > 832: gera direto na resolucao final, sem hi-res fix (treme com 81 quadros)",
    )
    parser.add_argument("--passos", type=int, default=None, help="Somente wan22-5b: passos do sampler (padrao 20)")
    parser.add_argument(
        "--upscale",
        type=lambda v: tuple(int(x) for x in v.lower().split("x")),
        default=None,
        metavar="LxA",
        help="Depois de gerar, amplia com 4x-UltraSharp para LxA (ex.: 1280x720). Jeito leve de ter 720p com o 14B",
    )
    parser.add_argument(
        "--interpolar",
        type=int,
        default=None,
        metavar="N",
        help="RIFE: multiplica o fps por N (padrao wan22 2 -> 16 vira 32fps; 5B/ltx 1 = desligado)",
    )
    parser.add_argument(
        "--crf",
        type=float,
        default=14,
        help="Qualidade do mp4 final (H.264): menor = mais nitido e maior. Padrao 14 (~7 Mbps em 720p); o ComfyUI usa 23",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--saida", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--host", default="127.0.0.1:8188")
    parser.add_argument("--comfyui-output", type=Path, default=DEFAULT_COMFYUI_OUTPUT)
    parser.add_argument("--timeout-min", type=int, default=60)
    args = parser.parse_args()

    wan = args.modelo.startswith("wan22")
    cinco_b = args.modelo == "wan22-5b"
    if wan:
        args.modo = "i2v"  # os kits wan22 so tem imagem->video
    args.frames = args.frames or (121 if cinco_b else 81 if wan else 241)
    args.fps = args.fps or (24 if cinco_b else 16 if wan else 24)
    args.max_lado = args.max_lado or (1280 if cinco_b else 832 if wan else 1024)
    if args.interpolar is None:
        args.interpolar = 2 if wan and not cinco_b else 1

    if args.video:
        if not args.video.exists():
            parser.error(f"Video nao encontrado: {args.video}")
    elif not args.prompt:
        parser.error("--prompt e obrigatorio (ou use --video para so pos-processar)")
    elif args.modo == "i2v" and not args.imagem:
        parser.error("--imagem e obrigatorio quando --modo i2v")
    if not args.video and args.modo == "i2v" and not args.imagem.exists():
        parser.error(f"Imagem nao encontrada: {args.imagem}")

    try:
        inicio = time.time()
        if args.video:
            origem, nome_arquivo = args.video, args.video.name
            fps = fps_do_video(args.video, args.fps)
        else:
            tem_pos = bool(args.upscale) or args.interpolar > 1
            workflow = definir_crf(montar_workflow(args), CRF_INTERMEDIARIO if tem_pos else args.crf)
            nome_arquivo, subpasta = executar(args.host, workflow, args.timeout_min)
            origem = args.comfyui_output / subpasta / nome_arquivo
            fps = args.fps

        if args.upscale:
            largura, altura = args.upscale
            print(f"Upscale para {largura}x{altura} (4x-UltraSharp)...")
            # tira o modelo de video da RAM/VRAM antes: o upscale de 81 quadros ocupa varios GB
            chamar_api(args.host, "/free", {"unload_models": True, "free_memory": True}, metodo="POST")
            nome_arquivo, subpasta = executar(
                args.host,
                definir_crf(
                    montar_workflow_upscale(args.host, origem, largura, altura),
                    CRF_INTERMEDIARIO if args.interpolar > 1 else args.crf,
                ),
                args.timeout_min,
            )
            origem = args.comfyui_output / subpasta / nome_arquivo

        if args.interpolar > 1:
            print(f"Interpolando {fps:g} -> {fps * args.interpolar:g} fps (RIFE)...")
            chamar_api(args.host, "/free", {"unload_models": True, "free_memory": True}, metodo="POST")
            nome_arquivo, subpasta = executar(
                args.host,
                definir_crf(montar_workflow_interpolar(args.host, origem, args.interpolar, fps), args.crf),
                args.timeout_min,
            )
            origem = args.comfyui_output / subpasta / nome_arquivo

        args.saida.mkdir(parents=True, exist_ok=True)
        destino = args.saida / nome_arquivo
        destino.write_bytes(origem.read_bytes())

        print(f"\nVideo salvo em: {destino} ({(time.time() - inicio) / 60:.1f} min)")

    except ConnectionError as e:
        print(f"[erro] {e}")
        sys.exit(1)
    except (RuntimeError, TimeoutError) as e:
        print(f"[erro] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
