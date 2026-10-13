"""Baixa os pesos de video para a pasta de modelos do ComfyUI.

Kits: wan22 (padrao, Wan 2.2 14B imagem->video + LoRAs de 4 passos) e ltx
(Sulphur-2 / LTX-2.3, descontinuado).

Uso:
    python setup_models.py
    python setup_models.py --kit ltx
    python setup_models.py --comfyui-models "D:\\outro_caminho\\ComfyUI\\models"
"""
import argparse
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

DEFAULT_COMFYUI_MODELS = (
    Path.home()
    / "AppData"
    / "Local"
    / "Comfy-Desktop"
    / "ComfyUI-Shared"
    / "models"
)

WAN22 = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"

# (repo_id, filename no repo, subpasta de destino em models/, tamanho aproximado em GB)
KITS = {}
KITS["wan22"] = [
    (WAN22, "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "diffusion_models", 13.3),
    (WAN22, "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "diffusion_models", 13.3),
    (WAN22, "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "loras", 1.1),
    (WAN22, "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", "loras", 1.1),
    (WAN22, "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders", 6.3),
    (WAN22, "split_files/vae/wan_2.1_vae.safetensors", "vae", 0.2),
]
# Qwen-Image 2.1 edit: compoe a 1a cena a partir de N imagens de referencia
# (personagens/cenario), que depois o Wan 2.2 anima (workflows/personagens_i2v.json).
QWEN21 = "Comfy-Org/Qwen-Image-2.1"
KITS["personagens"] = KITS["wan22"] + [
    (QWEN21, "diffusion_models/qwen_image_2.1_int8_convrot.safetensors", "diffusion_models", 6.8),
    (QWEN21, "text_encoders/qwen3vl_8b_int8_convrot.safetensors", "text_encoders", 8.7),
    (QWEN21, "vae/qwen_image_2.1_vae_bf16.safetensors", "vae", 0.6),
    (QWEN21, "loras/qwen_image_2.1_turbo_lora_avg_rank_178_bf16.safetensors", "loras", 0.9),
]
KITS["ltx"] = [
    ("SulphurAI/Sulphur-2-base", "sulphur_dev_fp8mixed.safetensors", "checkpoints", 29.2),
    (
        "SulphurAI/Sulphur-2-base",
        "distill_loras/ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors",
        "loras",
        0.7,
    ),
    ("Comfy-Org/ltx-2", "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors", "text_encoders", 9.5),
    ("Kijai/LTX2.3_comfy", "vae/taeltx2_3.safetensors", "vae", 0.2),
    ("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.0.safetensors", "latent_upscale_models", 0.5),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comfyui-models",
        type=Path,
        default=DEFAULT_COMFYUI_MODELS,
        help="Caminho para a pasta models/ do ComfyUI (padrao: instalacao do ComfyUI Desktop)",
    )
    parser.add_argument("--kit", choices=list(KITS), default="wan22", help="Conjunto de modelos (padrao: wan22)")
    parser.add_argument("--sim", action="store_true", help="Mostra o plano sem baixar nada")
    parser.add_argument("-y", "--yes", action="store_true", help="Nao pergunta antes de baixar")
    args = parser.parse_args()

    models_dir = args.comfyui_models
    if not models_dir.exists():
        print(f"[erro] Pasta de modelos do ComfyUI nao encontrada: {models_dir}")
        print("Use --comfyui-models para apontar o caminho correto.")
        sys.exit(1)

    print(f"Pasta de modelos do ComfyUI: {models_dir}\n")
    total_gb = 0.0
    plano = []
    for repo_id, filename, subpasta, tamanho_gb in KITS[args.kit]:
        dest_dir = models_dir / subpasta
        dest_name = Path(filename).name
        dest_path = dest_dir / dest_name
        ja_existe = dest_path.exists()
        plano.append((repo_id, filename, dest_dir, dest_path, ja_existe))
        status = "ja existe, sera pulado" if ja_existe else f"~{tamanho_gb:.1f} GB"
        print(f"  [{subpasta}/{dest_name}] {status}")
        if not ja_existe:
            total_gb += tamanho_gb

    print(f"\nTotal a baixar: ~{total_gb:.1f} GB")

    if args.sim:
        return

    if total_gb > 0 and not args.yes:
        resposta = input("Continuar com o download? [s/N] ").strip().lower()
        if resposta != "s":
            print("Cancelado.")
            return

    for repo_id, filename, dest_dir, dest_path, ja_existe in plano:
        if ja_existe:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nBaixando {filename} de {repo_id} ...")
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=dest_dir,
        )
        # hf_hub_download preserva subpastas do repo (ex.: "distill_loras/arquivo.safetensors");
        # move o arquivo para a raiz da pasta de destino do ComfyUI se necessario.
        baixado_em = dest_dir / filename
        if baixado_em != dest_path and baixado_em.exists():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            baixado_em.replace(dest_path)
            # limpa as subpastas intermediarias que ficaram vazias
            pasta = baixado_em.parent
            while pasta != dest_dir and not any(pasta.iterdir()):
                pasta.rmdir()
                pasta = pasta.parent

    print("\nPronto. Modelos instalados em:", models_dir)


if __name__ == "__main__":
    main()
