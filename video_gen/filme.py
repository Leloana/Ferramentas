"""Filme longo com continuidade: roteiro JSON -> tomadas de ~5s -> um mp4.

Continuidade de personagem: cada tomada "nova" tem o 1o quadro composto pelo
Qwen-Image 2.1 (modo edicao) a partir das imagens de referencia dos personagens
(e, se pedido, do ultimo quadro de outra tomada como referencia de lugar).
Continuidade de acao: tomadas "continua" comecam do ultimo quadro da anterior.
Cada tomada: Wan 2.2 14B hi-res fix (720p) -> RIFE 32fps -> som com MMAudio.

Retomavel: o que ja existe em <saida>/ e pulado. Uso:
    python filme.py filme/trilha.json
    python filme.py filme/trilha.json --ate 5        # so as 5 primeiras tomadas
"""
import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import gerar_video as g

RAIZ = Path(__file__).parent


def qwen_cena(host: str, prompt: str, refs: list[Path], seed: int, destino: Path) -> None:
    """Qwen-Image 2.1 com N imagens de referencia (<image1>, <image2>, ...)."""
    workflow = json.loads((g.WORKFLOWS_DIR / "qwen21_t2i.json").read_text(encoding="utf-8"))
    workflow["25"]["inputs"]["prompt"] = prompt
    for i, ref in enumerate(refs, 1):
        workflow[f"4{i}"] = {"class_type": "LoadImage", "inputs": {"image": g.enviar_imagem(host, ref)}}
        workflow["25"]["inputs"][f"images.image_{i}"] = [f"4{i}", 0]
    workflow["27"]["inputs"]["seed"] = seed
    resposta = g.chamar_api(host, "/prompt", {"prompt": workflow, "client_id": "filme"}, metodo="POST")
    if "error" in resposta:
        raise RuntimeError(f"Qwen rejeitou: {resposta['error']} {resposta.get('node_errors', '')}")
    entrada = g.aguardar_conclusao(host, resposta["prompt_id"], 20)
    imagem = entrada["outputs"]["29"]["images"][0]
    destino.write_bytes((g.DEFAULT_COMFYUI_OUTPUT / imagem.get("subfolder", "") / imagem["filename"]).read_bytes())


def montar_prompt(texto: str, refs_nomes: list[str]) -> str:
    """Troca {lia}, {bento}, {lugar}... por <image1>, <image2>... na ordem das refs."""
    for i, nome in enumerate(refs_nomes, 1):
        texto = texto.replace("{" + nome + "}", f"<image{i}>")
    return texto


def ultimo_quadro(video: Path, destino: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(video), "-update", "1", "-q:v", "1", str(destino)],
        check=True,
    )


def gerar_tomada(host: str, tomada: dict, imagem: Path, pasta: Path, seed: int, estilo: str) -> Path:
    args = argparse.Namespace(
        imagem=imagem, max_lado=1280, nativo=False, frames=81, fps=16, seed=seed,
        prompt=f"{tomada['movimento']} {estilo}".strip(), negativo=None, host=host,
    )
    nome, sub = g.executar(host, g.definir_crf(g.montar_workflow_wan22(args), g.CRF_INTERMEDIARIO), 60)
    bruto = pasta / "brutos" / f"{tomada['id']}.mp4"
    bruto.write_bytes((g.DEFAULT_COMFYUI_OUTPUT / sub / nome).read_bytes())
    ultimo_quadro(bruto, pasta / "quadros" / f"{tomada['id']}_fim.png")

    g.chamar_api(host, "/free", {"unload_models": True, "free_memory": True}, metodo="POST")
    nome, sub = g.executar(host, g.definir_crf(g.montar_workflow_interpolar(host, bruto, 2, 16), 14), 30)
    interp = pasta / "brutos" / f"{tomada['id']}_32fps.mp4"
    interp.write_bytes((g.DEFAULT_COMFYUI_OUTPUT / sub / nome).read_bytes())

    com_som = g.adicionar_audio(host, interp, tomada.get("som", ""), seed, 20, g.DEFAULT_COMFYUI_OUTPUT)
    final = pasta / "tomadas" / f"{tomada['id']}.mp4"
    com_som.replace(final)
    interp.unlink()
    return final


def juntar(pasta: Path, ids: list[str], destino: Path, final: bool) -> None:
    """Previa: concat sem recomprimir. Final: recomprime com fade curto no audio de cada corte."""
    clipes = [pasta / "tomadas" / f"{i}.mp4" for i in ids if (pasta / "tomadas" / f"{i}.mp4").exists()]
    if not clipes:
        return
    if not final:
        lista = pasta / "lista.txt"
        lista.write_text("".join(f"file '{c.as_posix()}'\n" for c in clipes), encoding="utf-8")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
                        "-c", "copy", str(destino)], check=True)
        return
    entradas, filtros, pares = [], [], []
    for k, c in enumerate(clipes):
        entradas += ["-i", str(c)]
        filtros.append(f"[{k}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                       f"afade=t=in:d=0.08,areverse,afade=t=in:d=0.25,areverse[a{k}]")
        pares.append(f"[{k}:v][a{k}]")
    filtro = ";".join(filtros) + ";" + "".join(pares) + f"concat=n={len(clipes)}:v=1:a=1[v][a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destino)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roteiro", type=Path)
    parser.add_argument("--ate", type=int, default=None, help="Gera so as N primeiras tomadas")
    parser.add_argument("--host", default="127.0.0.1:8188")
    args = parser.parse_args()

    roteiro = json.loads(args.roteiro.read_text(encoding="utf-8"))
    pasta = RAIZ / "output" / f"filme_{roteiro['nome']}"
    for sub in ("refs", "quadros", "brutos", "tomadas"):
        (pasta / sub).mkdir(parents=True, exist_ok=True)
    seed_base = roteiro.get("seed", 1000)
    estilo = roteiro.get("estilo_movimento", "")

    # Referencias dos personagens (geradas uma vez; dá pra trocar o arquivo à mão)
    refs = {}
    for nome, info in roteiro["personagens"].items():
        refs[nome] = pasta / "refs" / f"{nome}.png"
        if not refs[nome].exists():
            print(f"Referencia {nome}...")
            qwen_cena(args.host, info["prompt"], [], seed_base, refs[nome])

    tomadas = roteiro["tomadas"][: args.ate]
    ids = [t["id"] for t in tomadas]
    inicio_total = time.time()
    for n, tomada in enumerate(tomadas):
        final = pasta / "tomadas" / f"{tomada['id']}.mp4"
        if final.exists():
            continue
        t0 = time.time()
        seed = seed_base + n * 7
        quadro = pasta / "quadros" / f"{tomada['id']}.png"
        if tomada["tipo"] == "continua":
            anterior = tomadas[n - 1]["id"]
            quadro = pasta / "quadros" / f"{anterior}_fim.png"
            if not quadro.exists():
                print(f"[pulada] {tomada['id']}: a tomada {anterior} nao foi gerada", flush=True)
                continue
        elif not quadro.exists():
            nomes = list(tomada.get("refs", []))
            imagens = [refs[r] for r in nomes]
            texto = tomada["cena"]
            lugar = pasta / "quadros" / f"{tomada.get('lugar')}_fim.png"
            if tomada.get("lugar") and lugar.exists():
                nomes.append("lugar")
                imagens.append(lugar)
                # o quadro de lugar costuma ter os personagens: sem isso o Qwen os duplica
                texto += " Use {lugar} only as a reference for the location, landscape and lighting, not for people or animals."
            estilo_cena = roteiro.get("estilo_cena", "")
            if tomada.get("refs"):  # a descricao dos personagens so entra se eles estao na tomada
                estilo_cena += " " + roteiro.get("estilo_personagens", "")
            qwen_cena(args.host, montar_prompt(texto, nomes) + " " + estilo_cena.strip(), imagens, seed, quadro)
        try:
            gerar_tomada(args.host, tomada, quadro, pasta, seed, estilo)
        except (RuntimeError, TimeoutError, subprocess.CalledProcessError) as e:
            print(f"[erro] tomada {tomada['id']}: {e}", flush=True)
            continue
        juntar(pasta, ids, pasta / "previa.mp4", final=False)
        feitas = sum((pasta / "tomadas" / f"{i}.mp4").exists() for i in ids)
        print(f"ok {tomada['id']} ({feitas}/{len(ids)}) em {(time.time() - t0) / 60:.1f} min "
              f"- total {(time.time() - inicio_total) / 60:.0f} min", flush=True)

    if all((pasta / "tomadas" / f"{i}.mp4").exists() for i in ids):
        juntar(pasta, ids, pasta / f"{roteiro['nome']}.mp4", final=True)
        print(f"Filme pronto: {pasta / (roteiro['nome'] + '.mp4')}")


if __name__ == "__main__":
    sys.exit(main())
