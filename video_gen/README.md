# video_gen — Gerador de vídeo local (Sulphur-2 / LTX-2.3 via ComfyUI)

Gera vídeos (texto→vídeo e imagem→vídeo, com áudio sincronizado) usando o
[Sulphur-2-base](https://huggingface.co/SulphurAI/Sulphur-2-base), um fine-tune
"uncensored" do modelo **LTX-2.3** (Lightricks, 22B parâmetros), rodando
localmente através do ComfyUI Desktop já instalado na máquina.

Este projeto **não instala o ComfyUI** — ele assume que o ComfyUI Desktop já
está presente e apenas baixa os pesos do modelo para dentro dele e envia jobs
de geração pela API HTTP.

## Aviso sobre hardware

O LTX-2.3 é um modelo de 22 bilhões de parâmetros. Numa GPU de 12GB de VRAM
(ex.: RTX 4070), o ComfyUI faz *offload* automático de partes do modelo para a
RAM, então a geração funciona, mas é **bem mais lenta** do que em placas de
16GB+. Espere alguns minutos por vídeo. Feche outros programas que usem a GPU
antes de gerar.

Este é um modelo "uncensored" de uso local — a responsabilidade pelo conteúdo
gerado é de quem o utiliza.

## Pré-requisitos

1. ComfyUI Desktop instalado e **aberto** (a API precisa estar ativa em
   `http://127.0.0.1:8188` — é a porta padrão do ComfyUI Desktop).
2. ComfyUI atualizado para uma versão recente (o suporte a LTX-2.3 é nativo,
   sem custom nodes, mas precisa de uma build recente do ComfyUI core).
3. ~40GB de espaço em disco livre para os modelos.

## Setup (uma vez)

```powershell
cd video_gen
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup_models.py
```

O `setup_models.py` baixa (via Hugging Face Hub) os seguintes arquivos para a
pasta `models/` do ComfyUI Desktop (`~\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models`):

| Arquivo | Origem | Pasta destino |
|---|---|---|
| `sulphur_dev_fp8mixed.safetensors` (~29GB) | SulphurAI/Sulphur-2-base | `checkpoints/` |
| LoRA distilled (~0.7GB) | SulphurAI/Sulphur-2-base | `loras/` |
| `gemma_3_12B_it_fp4_mixed.safetensors` (~9.5GB, text encoder) | Comfy-Org/ltx-2 | `text_encoders/` |
| `taeltx2_3.safetensors` (VAE leve) | Kijai/LTX2.3_comfy | `vae/` |
| upscaler espacial x2 | Lightricks/LTX-2.3 | `latent_upscale_models/` |

Se o script for interrompido, rode de novo — ele pula arquivos já baixados.

## Uso

Com o ComfyUI Desktop aberto:

**Texto → vídeo:**
```powershell
python gerar_video.py --prompt "um gato astronauta flutuando no espaco, cinematico"
```

**Imagem → vídeo:**
```powershell
python gerar_video.py --modo i2v --imagem foto.png --prompt "a cena ganha vida lentamente"
```

Opções úteis: `--frames` (padrão 241 ≈ 10s a 24fps), `--largura`/`--altura`
(somente t2v, padrão 768x512), `--seed` (para reproduzir o mesmo resultado),
`--saida` (pasta onde o vídeo final é copiado, padrão `video_gen/output/`).

O vídeo gerado é copiado para `video_gen/output/` e o caminho final é impresso
no terminal ao concluir.

## Solução de problemas

- **"Nao foi possivel falar com o ComfyUI"**: abra o ComfyUI Desktop antes de
  rodar o script.
- **Erro de nó/modelo faltando ao enviar o workflow**: rode
  `python setup_models.py` novamente e confirme que os 5 arquivos estão nas
  pastas corretas dentro de `ComfyUI-Shared/models/`.
- **Geração muito lenta ou travando**: normal no hardware de 12GB VRAM; feche
  outros programas pesados de GPU e aguarde — o ComfyUI está fazendo streaming
  de pesos entre RAM e VRAM.
