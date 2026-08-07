# video_gen — Gerador de vídeo local (Sulphur-2 / LTX-2.3 via ComfyUI)

Gera vídeos (texto→vídeo e imagem→vídeo, com áudio sincronizado) usando o
[Sulphur-2-base](https://huggingface.co/SulphurAI/Sulphur-2-base), um fine-tune
"uncensored" do modelo **LTX-2.3** (Lightricks, 22B parâmetros), rodando
localmente através do ComfyUI Desktop já instalado na máquina.

Este projeto **não instala o ComfyUI** — ele assume que o ComfyUI Desktop já
está presente e apenas baixa os pesos do modelo para dentro dele e envia jobs
de geração pela API HTTP.

## Aviso sobre o conteúdo gerado (importante)

Em teste real feito durante o desenvolvimento desta ferramenta, um prompt
totalmente neutro ("um farol na costa ao entardecer, ondas quebrando
suavemente, céu alaranjado" — sem nenhuma menção a pessoas) gerou por padrão
uma figura humana fotorrealista sem roupa. Ou seja: **este modelo "uncensored"
tende a gerar nudez/conteúdo adulto mesmo quando o prompt não pede isso**, não
é algo que só acontece se você pedir explicitamente.

Coisas a ter em mente:
- Não assuma que um prompt inocente vai gerar um resultado inocente — confira
  o vídeo antes de reaproveitar, exibir ou compartilhar.
- Para reduzir a chance disso, adicione termos ao `--negativo` (ex.: "nudity,
  naked, nsfw") — mas dado que o modelo foi ajustado justamente para remover
  esse tipo de filtro, isso não é garantia.
- A pasta `output/` não é versionada no git (está no `.gitignore`) exatamente
  por isso.
- A responsabilidade pelo conteúdo gerado e por como ele é usado é de quem
  roda a ferramenta.

## Aviso sobre hardware

O LTX-2.3 é um modelo de 22 bilhões de parâmetros. Numa GPU de 12GB de VRAM
(ex.: RTX 4070), o ComfyUI faz *offload* automático de partes do modelo para a
RAM, então a geração funciona, mas é **bem mais lenta** do que em placas de
16GB+. Espere alguns minutos por vídeo. Feche outros programas que usem a GPU
antes de gerar.

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

### Modo rápido vs. `--qualidade`

Por padrão a geração usa a receita "distilled": poucos passos de sampling e
CFG praticamente desligado, feita pra ser rápida. Isso deixa o vídeo com
blur/pouco detalhe. Use `--qualidade` para trocar a primeira fase da geração
por CFG real (3.6) e 50 passos — o mesmo checkpoint uncensored, só que com a
receita de sampling completa. Fica bem mais nítido, mas cada vídeo demora
consideravelmente mais no hardware de 12GB VRAM.

```powershell
python gerar_video.py --qualidade --prompt "um farol na costa ao entardecer"
```

### Dica de prompt: áudio

O LTX-2.3 gera vídeo com áudio sincronizado, mas o mesmo texto do prompt
alimenta tanto o vídeo quanto o áudio. Se o prompt só descrever a cena
visualmente, o modelo às vezes "narra" o próprio prompt em voz alta em vez de
gerar som ambiente. Para reduzir isso, descreva também o som desejado:

```
--prompt "um farol na costa ao entardecer, ondas quebrando suavemente. Audio: som de ondas quebrando, gaivotas ao longe, vento leve"
```

O negativo padrão já inclui termos contra narração/voz
(`voiceover, narration, spoken text, person talking, speech, ...`), mas isso
não é garantido — é uma tendência do modelo, não um filtro que se desliga.

## Solução de problemas

- **"Nao foi possivel falar com o ComfyUI"**: abra o ComfyUI Desktop antes de
  rodar o script.
- **Erro de nó/modelo faltando ao enviar o workflow**: rode
  `python setup_models.py` novamente e confirme que os 5 arquivos estão nas
  pastas corretas dentro de `ComfyUI-Shared/models/`.
- **Geração muito lenta ou travando**: normal no hardware de 12GB VRAM; feche
  outros programas pesados de GPU e aguarde — o ComfyUI está fazendo streaming
  de pesos entre RAM e VRAM.
