"""Script de automação para download dos modelos do Qwen-Image-2.1 e LoRAs
otimizados para 12GB VRAM (versões int8_convrot).

Baixa diretamente do Hugging Face com suporte a continuação de download
interrompido (HTTP Range) e barra de progresso.

Uso:
    python scripts/download_qwen_models.py --comfy-dir /caminho/para/ComfyUI
    # Se omitido, tenta detectar as pastas comuns do ComfyUI Desktop
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

# Modelos recomendados para RTX 4070 (12GB VRAM)
DOWNLOADS = [
    {
        "nome": "Qwen-Image-2.1 Diffusion Model (INT8)",
        "subpasta": "models/diffusion_models",
        "arquivo": "qwen_image_2.1_int8_convrot.safetensors",
        "url": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors",
        "tamanho_aprox_mb": 7200,
    },
    {
        "nome": "Qwen3-VL-8B Text Encoder (INT8)",
        "subpasta": "models/text_encoders",
        "arquivo": "qwen3vl_8b_int8_convrot.safetensors",
        "url": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors",
        "tamanho_aprox_mb": 4600,
    },
    {
        "nome": "Qwen-Image-2.1 VAE (BF16)",
        "subpasta": "models/vae",
        "arquivo": "qwen_image_2.1_vae_bf16.safetensors",
        "url": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors",
        "tamanho_aprox_mb": 350,
    },
    {
        "nome": "LoRA Qwen2.1 Anime Consistency",
        "subpasta": "models/loras",
        "arquivo": "Qwen2.1_Anime_consistency.safetensors",
        "url": "https://huggingface.co/WarmBloodAban/Qwen-Image-2.1-LoRAs/resolve/main/Qwen2.1_Anime_consistency.safetensors",
        "tamanho_aprox_mb": 150,
    },
    {
        "nome": "LoRA Modern Anime Style",
        "subpasta": "models/loras",
        "arquivo": "qwen-image-modern-anime-lora.safetensors",
        "url": "https://huggingface.co/alfredplpl/qwen-image-modern-anime-lora/resolve/main/qwen-image-modern-anime-lora.safetensors",
        "tamanho_aprox_mb": 220,
    },
]

LOCAIS_COMUNS_COMFY = [
    Path.home() / "ComfyUI",
    Path.home() / "AppData/Local/Comfy-Desktop/ComfyUI-Installs/ComfyUI/ComfyUI",
    Path.home() / "marcelo/ComfyUI",
]


def detectar_comfy_dir() -> Path | None:
    for p in LOCAIS_COMUNS_COMFY:
        if p.exists() and (p / "models").exists():
            return p
    return None


def baixar_arquivo(url: str, destino: Path, nome_legivel: str) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = destino.with_suffix(destino.suffix + ".part")

    baixado = temp_dest.stat().st_size if temp_dest.exists() else 0

    req = Request(url, headers={"User-Agent": "tts-platform-downloader"})
    if baixado > 0:
        req.add_header("Range", f"bytes={baixado}-")

    try:
        with urlopen(req, timeout=30) as resp:
            tamanho_total = resp.headers.get("Content-Length")
            if tamanho_total:
                tamanho_total = int(tamanho_total) + baixado
            else:
                tamanho_total = None

            modo = "ab" if baixado > 0 else "wb"
            with open(temp_dest, modo) as f:
                bloco = 1024 * 1024  # 1MB
                while True:
                    dados = resp.read(bloco)
                    if not dados:
                        break
                    f.write(dados)
                    baixado += len(dados)
                    if tamanho_total:
                        pct = (baixado / tamanho_total) * 100
                        mb_atual = baixado / (1024 * 1024)
                        mb_total = tamanho_total / (1024 * 1024)
                        sys.stdout.write(f"\r  [{pct:5.1f}%] {mb_atual:.1f} MB / {mb_total:.1f} MB")
                    else:
                        mb_atual = baixado / (1024 * 1024)
                        sys.stdout.write(f"\r  {mb_atual:.1f} MB baixados...")
                    sys.stdout.flush()

        temp_dest.rename(destino)
        print("\n  Concluído com sucesso!")
    except Exception as e:
        print(f"\n  Erro durante o download: {e}")
        print(f"  Você pode tentar baixar manualmente pelo link: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-dir", type=Path, default=None, help="Caminho raiz do ComfyUI")
    args = parser.parse_args()

    comfy_dir = args.comfy_dir or detectar_comfy_dir()
    if not comfy_dir:
        print("ComfyUI não foi detectado automaticamente nos caminhos padrão.")
        comfy_input = input("Por favor, digite o caminho da sua pasta raiz do ComfyUI: ").strip()
        if not comfy_input:
            print("Caminho não fornecido. Abortando.")
            sys.exit(1)
        comfy_dir = Path(comfy_input).expanduser().resolve()

    if not (comfy_dir / "models").exists():
        print(f"Aviso: pasta {comfy_dir / 'models'} não encontrada. Criando estrutura de pastas...")
        (comfy_dir / "models").mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"Preparando download dos modelos Qwen-Image-2.1 para: {comfy_dir}")
    print("Otimizado para RTX 4070 (12GB VRAM)")
    print("=" * 60)

    for item in DOWNLOADS:
        pasta_destino = comfy_dir / item["subpasta"]
        arquivo_destino = pasta_destino / item["arquivo"]

        print(f"\n>> {item['nome']} (~{item['tamanho_aprox_mb']} MB)")
        print(f"   Destino: {arquivo_destino}")

        if arquivo_destino.exists() and arquivo_destino.stat().st_size > 1024 * 1024 * 10:
            print("   [Já existe e está baixado. Pulando.]")
            continue

        baixar_arquivo(item["url"], arquivo_destino, item["nome"])

    print("\n" + "=" * 60)
    print("Todos os modelos estão prontos no seu ComfyUI!")
    print("=" * 60)


if __name__ == "__main__":
    main()
