# Modelos locais para RTX 4070 (12 GB) + 32 GB RAM

O melhor modelo aberto de cada área que cabe nessa máquina, escolhido por benchmark público.
Levantamento de 06/10/2026. Regra usada: o primeiro colocado do benchmark que roda em 12 GB de VRAM
(com offload pra RAM quando precisa). Quando o topo do ranking não cabe, está dito na linha.

## Escolhas

| Área | Modelo | Benchmark | Alternativa |
| --- | --- | --- | --- |
| Texto e código agêntico (dia a dia) | **Qwen3.6-35B-A3B** UD-Q4_K_XL | SWE-bench Verified 73,4 · Terminal-Bench 2.0 51,5 · LiveCodeBench 80,4 | gpt-oss-20b (SWE-bench 60,7) |
| Texto e código (máxima qualidade, lento) | **Qwen3.8-27B** UD-Q4_K_XL | AA Intelligence Index 34 contra 18 do 3.6-35B-A3B · Terminal-Bench 2.1 73,0 | Qwen3.6-27B (SWE-bench 77,2) |
| Imagem | **Qwen-Image-2.1** INT8 | 1º entre os abertos na AA Text-to-Image (Elo 1036) | Z-Image Turbo / FLUX.2 klein 9B (Elo 941, bem mais rápidos) |
| Vídeo (com áudio) | **LTX-2.5 Distilled** GGUF Q4_K_S | AA Image-to-Video aberto: Elo 1038 · Text-to-Video aberto: Elo 946 | Wan 2.2 14B (movimento mais realista, ~6x mais lento, sem áudio) |
| Música (com voz) | **ACE-Step 1.5 XL Turbo** | SongEval coerência 4,72 / musicalidade 4,67 · AudioBox CU 8,12 (maior entre os abertos) | HeartMuLa 3B (4,68 / 4,55, melhor pronúncia da letra) |
| TTS com clonagem | **Fish Audio S2 Pro** FP8 | AA Speech Arena aberto: Elo 1117 (2º) · 80+ línguas, pt incluso | Kokoro 82M (Elo 1064, pt-BR, sem clonagem, roda em qualquer coisa) |
| STT (pt) | **Whisper large-v3** (faster-whisper) | FLEURS pt WER 3,88 | Voxtral Mini 3B (WER 3,84, empate técnico, 3x maior) |

Por que não o primeiro do ranking em alguns casos:

- **Texto:** o Qwen3.8-27B é bem mais inteligente, mas é denso. Em Q4 tem 17,6 GB e não cabe na 4070, então roda dividido com a CPU a uns 6-10 tok/s. O 35B-A3B é MoE com 3B ativos: os experts ficam na RAM e ele roda a ~30-38 tok/s numa 4070. Pra agente que faz muitas chamadas, velocidade ganha. Use o 27B quando a tarefa for difícil e der pra esperar.
- **Vídeo:** MiniMax H3 (Elo 1181) e MAGI-2 (1093) estão acima, mas não rodam em 12 GB. Wan 2.5/2.6 não têm pesos abertos.
- **TTS:** o 1º é o Breeze TTS 2 (Elo 1216), mas só roda em Linux, não tem pt claro na doc e a licença é não comercial. O Fish S2 Pro também é licença de pesquisa (não comercial); se for usar comercialmente, o Kokoro é Apache 2.0. As margens de erro do arena são grandes (±120 a ±160).
- **XTTS-v2**, que o `tts_platform_pt` usa hoje, está em 14º com Elo 916. Vale testar o Fish S2 no lugar.
- **STT:** Voxtral Mini 3B tem WER 0,04 menor, dentro da margem. O Whisper large-v3 fica por ter timestamp por palavra, 1,5 GB e já estar no karaokê.

## Onde roda cada um

Tudo no PC Windows da 4070. Esta máquina Linux (RX 550) não roda nada disso.

| Área | Como roda | Disco |
| --- | --- | --- |
| Texto/código | llama.cpp (`llama-server`, API compatível com OpenAI na porta 8080) | 22,4 GB (+17,6 GB do 27B) |
| Imagem | ComfyUI Desktop (já instalado, workflows em `tts_platform_pt/comfy/`) | 17,4 GB |
| Vídeo | ComfyUI Desktop + nó ComfyUI-GGUF | 32 GB |
| Música | ACE-Step 1.5 (Gradio na porta 7860) | 26 GB |
| TTS | Fish Speech no WSL ou Docker (oficial não suporta Windows nativo) | 8 GB |
| STT | faster-whisper (Python) | 1,5 GB |

Total com tudo: ~125 GB. Não rodar dois ao mesmo tempo: cada um usa a VRAM inteira.

## Como usar

No PowerShell do PC da 4070, dentro desta pasta:

```powershell
# baixa tudo (ou escolha: -Areas texto,imagem,video,musica,tts,stt,texto-max)
.\baixar.ps1 -Destino D:\IA -ComfyModels "$env:USERPROFILE\Documents\ComfyUI\models"

# sobe o LLM (padrão: Qwen3.6-35B-A3B; -Max sobe o Qwen3.8-27B)
.\rodar_llm.ps1
```

O `baixar.ps1` instala o `hf` (via uv) e o llama.cpp CUDA se faltarem, e pula arquivo já baixado.

### Texto e código agêntico

`rodar_llm.ps1` sobe o `llama-server` em `http://localhost:8080/v1`. Qualquer agente que fale OpenAI
aponta pra lá (opencode, Continue, Cline, o `local_agent` deste repo trocando a base_url).

Ajuste fino da VRAM: `-CpuMoe` é quantas camadas mandam os experts pra RAM. Menor = mais rápido e
mais VRAM. Comece no padrão (30), olhe o `nvidia-smi` e desça até ficar perto de 11 GB.

Parâmetros de amostragem da Qwen pra código: temp 0,6, top-p 0,95, top-k 20 (já no script).

### Imagem

Se o `tts_platform_pt` já roda o Qwen-Image-2.1, não precisa baixar de novo: os arquivos são os mesmos.
Workflows prontos: `tts_platform_pt/comfy/image_qwen_image_2_1_t2i.json`. CFG 1.0, prompt em frase
natural, sem lista de tags.

### Vídeo

1. No ComfyUI Manager, instale o nó **ComfyUI-GGUF**.
2. Arraste pro ComfyUI o workflow `D:\IA\video\LTX 2.5 GGUF (WORKFLOW).json`.
3. Comece em 768x512, ~5 s, CFG 1.0 (é o distilled). Se estourar a VRAM, troque pro `Q3_K_M`.

O text encoder (Gemma 4 12B INT8, 15,4 GB) roda antes do vídeo e sai da VRAM, mas ocupa RAM.
Feche o resto antes de gerar.

### Música

```powershell
cd D:\IA\ACE-Step-1.5
uv sync
uv run acestep   # abre em http://localhost:7860
```

O `.env` já fica com o XL Turbo e o LM 1.7B. Com 12 GB ele liga offload e INT8 sozinho.
Se ficar lento demais, troque `ACESTEP_CONFIG_PATH` pra `acestep-v15-turbo` (2B, bem mais leve).

### TTS

Fish Speech não tem instalação Windows nativa. Pelo WSL:

```bash
git clone https://github.com/fishaudio/fish-speech && cd fish-speech
# checkpoint FP8 baixado pelo baixar.ps1 em D:\IA\tts\s2-pro-fp8
docker compose --profile webui up   # http://localhost:7860
```

Monte `/mnt/d/IA/tts/s2-pro-fp8` como `/app/checkpoints/s2-pro`. O FP8 usa ~12 GB e é de terceiro
(Benjonson/s2-pro-fp8); se não couber, há versão NF4 (scarxity/fish-speech-s2-pro-nf4).
Clonagem: 10 a 30 s de áudio de referência. Aceita tags de emoção tipo `[sussurrando]`.

### STT

```powershell
uv run --with faster-whisper python -c "from faster_whisper import WhisperModel; m=WhisperModel('large-v3', device='cuda', compute_type='float16'); print(' '.join(s.text for s in m.transcribe('audio.mp3', language='pt')[0]))"
```

## Fontes

- Qwen3.6-35B-A3B: [model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B), [BenchLM](https://benchlm.ai/models/qwen3-6-35b-a3b), [4070 a 37 tok/s](https://dev.to/kenimo49/qwen-36-vs-35-same-37-toks-on-rtx-4070-43-on-frontend-generation-3i0o)
- Qwen3.8-27B x Qwen3.6-35B-A3B: [Artificial Analysis](https://artificialanalysis.ai/models/releases/comparisons/qwen3-8-27b-vs-qwen3-6-35b-a3b), [review](https://www.orcarouter.ai/blog/qwen-3-8-27b-review)
- gpt-oss-20b: [model card](https://arxiv.org/pdf/2508.10925)
- Imagem: [AA Text-to-Image, abertos](https://artificialanalysis.ai/image/leaderboard/text-to-image?open-weights=true)
- Vídeo: [AA Image-to-Video, abertos](https://artificialanalysis.ai/video/leaderboard/image-to-video/open-weights), [AA Text-to-Video, abertos](https://artificialanalysis.ai/video/leaderboard/text-to-video/open-weights), [Wan 2.5/2.6 sem pesos](https://fuser.studio/articles/best-open-source-video-models), [LTX x Wan](https://magichour.ai/blog/ltx-2-3-vs-wan-2-2)
- Música: [ACE-Step 1.5 paper](https://arxiv.org/pdf/2602.00744), [HeartMuLa](https://arxiv.org/pdf/2601.10547), [requisitos XL](https://github.com/ace-step/ACE-Step-1.5)
- TTS: [AA Speech Arena, abertos](https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights), [Fish S2 Pro](https://huggingface.co/fishaudio/s2-pro), [Breeze TTS 2 licença](https://wavespeed.ai/blog/commercial-compliance/breeze-tts-2-review/)
- STT: [WER em português (FLEURS)](https://models.handy.computer/languages/pt)
