"""Script orquestrador que executa o pipeline completo de produção de um vídeo:
1. Síntese de áudio + alinhamento forçado (gerar_video.py)
2. Geração de imagens via ComfyUI / Qwen-Image-2.1 com continuidade (gerar_imagens.py)
3. Montagem do vídeo com animação Ken Burns e legendas sincronizadas (montar_video.py)

Uso:
    python3 scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima
    python3 scripts/executar_projeto.py Projetos/ideias/bruxas_da_noite_1942 --voz "Tais Galante"
    python3 scripts/executar_projeto.py Projetos/ideias/carga_dos_hussardos_1683 --pular-imagens
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def resolver_voz(pasta_projeto: Path, voz_arg: str | None) -> str | None:
    if voz_arg:
        return voz_arg

    arquivo_vozes = pasta_projeto / "vozes.md"
    if not arquivo_vozes.exists():
        return None

    conteudo = arquivo_vozes.read_text(encoding="utf-8").strip()
    # Tenta pegar a primeira voz recomendada no vozes.md
    for linha in conteudo.splitlines():
        linha = linha.strip()
        if ":" in linha:
            _, nome = linha.split(":", 1)
            return nome.strip()
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Executa o pipeline completo de produção para um projeto histórico.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "projeto",
        type=Path,
        help="Caminho da pasta do projeto (ex: Projetos/Video_11/musashi_duelo_ganryujima)",
    )
    parser.add_argument(
        "--voz",
        type=str,
        default=None,
        help="Nome da voz para síntese (se omitido, lê de vozes.md ou usa padrão)",
    )
    parser.add_argument(
        "--velocidade",
        type=float,
        default=1.20,
        help="Velocidade da narração (padrão: 1.20)",
    )
    parser.add_argument(
        "--workflow-t2i",
        type=Path,
        default=Path("comfy/image_qwen_image_2_1_t2i.json"),
        help="Workflow base de imagem (padrão: comfy/image_qwen_image_2_1_t2i.json)",
    )
    parser.add_argument(
        "--workflow-i2i",
        type=Path,
        default=Path("comfy/image_qwen_image_2_1_lora_i2i.json"),
        help=(
            "Workflow de referência/continuidade (padrão: "
            "comfy/image_qwen_image_2_1_lora_i2i.json — o i2i com o LoRA de "
            "consistência facial de anime; use image_qwen_image_2_1_i2i.json pra "
            "rodar sem o LoRA)"
        ),
    )
    parser.add_argument(
        "--pular-audio",
        action="store_true",
        help="Pula a etapa de áudio (usa manifesto já existente)",
    )
    parser.add_argument(
        "--pular-imagens",
        action="store_true",
        help="Pula a geração de imagens no ComfyUI",
    )
    parser.add_argument(
        "--pular-montagem",
        action="store_true",
        help="Pula a montagem final do vídeo em mp4",
    )
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:8011",
        help="URL do servidor TTS (padrão: http://127.0.0.1:8011)",
    )

    args = parser.parse_args()

    projeto = args.projeto.resolve()
    if not projeto.is_dir():
        print(f"Erro: pasta do projeto não encontrada: {projeto}", file=sys.stderr)
        sys.exit(1)

    roteiro = projeto / "texto.md"
    if not roteiro.exists():
        print(f"Erro: arquivo de roteiro 'texto.md' não encontrado em: {projeto}", file=sys.stderr)
        sys.exit(1)

    manifesto = projeto / "texto_manifesto.json"
    prompts_json = projeto / "texto_prompts.json"
    referencia_json = projeto / "texto_referencia.json"

    print("=" * 60)
    print(f"Iniciando pipeline de produção para: {projeto.name}")
    print("=" * 60)

    # 1. ETAPA DE ÁUDIO
    if not args.pular_audio:
        voz = resolver_voz(projeto, args.voz)
        cmd_audio = [
            sys.executable,
            "scripts/gerar_video.py",
            str(roteiro),
            "--velocidade",
            str(args.velocidade),
            "--server",
            args.server,
        ]
        if voz:
            cmd_audio.extend(["--voz", voz])

        print(f"\n[1/3] Sintetizando áudio (voz: {voz or 'padrão'})...")
        res = subprocess.run(cmd_audio)
        if res.returncode != 0:
            print(f"Erro na síntese de áudio (código {res.returncode})", file=sys.stderr)
            sys.exit(res.returncode)
    else:
        print("\n[1/3] Pulando síntese de áudio conforme solicitado.")

    if not manifesto.exists():
        print(f"Erro: manifesto {manifesto} não existe após etapa de áudio.", file=sys.stderr)
        sys.exit(1)

    # 2. ETAPA DE IMAGENS
    if not args.pular_imagens:
        if not prompts_json.exists():
            print(f"Aviso: {prompts_json.name} não encontrado. Pulando geração de imagens.")
        else:
            print("\n[2/3] Gerando imagens via ComfyUI (Qwen-Image-2.1)...")
            cmd_imagens = [
                sys.executable,
                "scripts/gerar_imagens.py",
                str(manifesto),
                "--workflow",
                str(args.workflow_t2i),
                "--prompts",
                str(prompts_json),
            ]
            if referencia_json.exists() and args.workflow_i2i.exists():
                cmd_imagens.extend([
                    "--referencia",
                    str(referencia_json),
                    "--referencia-workflow",
                    str(args.workflow_i2i),
                ])

            res = subprocess.run(cmd_imagens)
            if res.returncode != 0:
                print(f"Erro na geração de imagens (código {res.returncode})", file=sys.stderr)
                sys.exit(res.returncode)
    else:
        print("\n[2/3] Pulando geração de imagens conforme solicitado.")

    # 3. ETAPA DE MONTAGEM
    if not args.pular_montagem:
        print("\n[3/3] Montando vídeo final (9:16 com zoom e legendas)...")
        cmd_montagem = [
            sys.executable,
            "scripts/montar_video.py",
            str(manifesto),
        ]
        res = subprocess.run(cmd_montagem)
        if res.returncode != 0:
            print(f"Erro na montagem do vídeo (código {res.returncode})", file=sys.stderr)
            sys.exit(res.returncode)
    else:
        print("\n[3/3] Pulando montagem final conforme solicitado.")

    video_final = projeto / "video" / "texto_9x16.mp4"
    print("\n" + "=" * 60)
    if video_final.exists():
        print(f"PROCESSO CONCLUÍDO COM SUCESSO!")
        print(f"Vídeo gerado: {video_final}")
    else:
        print("Pipeline finalizado. Verifique a pasta do projeto.")
    print("=" * 60)


if __name__ == "__main__":
    main()
