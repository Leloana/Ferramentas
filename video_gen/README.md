# video_gen — Gerador de vídeo local via ComfyUI

## Padrão: Wan 2.2 14B imagem→vídeo (desde 2026-10-13)

Imagem (ex.: gerada no Z-Image/Krea2) + prompt → vídeo de ~5s, usando o Wan
2.2 14B I2V fp8 (dois modelos, high/low noise) com os LoRAs lightx2v de 4
passos. Só imagem→vídeo; texto→vídeo continua só no kit LTX abaixo.

```powershell
cd video_gen
.\venv\Scripts\python.exe setup_models.py -y      # ~35GB, uma vez (kit wan22)
# com o Comfy Desktop aberto ("Comfy Desktop\Comfy Desktop.exe", NAO o ComfyUI.exe antigo)
.\venv\Scripts\python.exe gerar_video.py --imagem foto.png --prompt "descreva o movimento, em ingles"
```

Opções: `--max-lado` (padrão 832), `--upscale 1280x720` (720p, ver abaixo), `--interpolar N` (padrão 2 → 32fps), `--frames` (padrão 81 = 5s a 16fps,
arredonda pra 4k+1), `--fps`, `--seed`, `--negativo`.

Medições na RTX 4070 12GB + 32GB RAM:
- **464x832, 81 frames: 2,7 min** no total (inclusive carregar os modelos). Boa
  movimentação, sem o "slow motion" típico.
- **720p: ver a seção abaixo** — em 2026-10-13 travou o PC; em 2026-10-14
  rodou em 7,6 min (1280x720 e 720x1280). Use `--max-lado 1280`.

## Fluidez: interpolação RIFE (padrão, desde 2026-10-14)

O Wan 2.2 14B gera a 16 fps, o que fica travado. Por padrão o script agora
passa o vídeo pelo **RIFE 4.9** (`workflows/interpolar_video.json`), que cria um
quadro entre cada par: **16 → 32 fps**, mesma duração, ~15 s a mais em 720p.
Os quadros inventados saem limpos (sem fantasma em pernas/guia/cachorro).

- `--interpolar 3` → 48 fps (~25 s em 720p); `--interpolar 1` desliga. Testado com
  um arqueiro soltando a flecha (objeto rápido): nos quadros criados a flecha
  avança em posições intermediárias, sem duplicar nem deixar rastro. O 5B (24 fps) e o LTX vêm desligados.
- Corrigir vídeo antigo sem gerar de novo: `gerar_video.py --video output/x.mp4`
  (dá pra combinar com `--upscale 1280x720`).
- Precisa do custom node [ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation)
  em `ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes` (`git clone`; as dependências já
  estavam na venv do ComfyUI). O peso `rife49.pth` baixa sozinho no 1º uso.
  O `rife426.pth` baixado pelo nó **não carrega** (state_dict com chaves `teacher.*`).

## 720p (testado em 2026-10-14)

Mesma imagem (casal passeando com golden retriever, gerada no Krea2 em 16:9),
mesmo prompt e seed, três caminhos:

| Caminho | Comando | Tempo | Resultado |
|---|---|---|---|
| 14B 832x464 + upscale | `gerar_video.py --imagem x.png --prompt "..." --upscale 1280x720` | 2,1 + 2,8 = **4,9 min** | Bom e mais rápido: luz estável, movimento natural, mas o UltraSharp deixa textura meio "pintada" |
| 5B nativo 1280x704 | `gerar_video.py --modelo wan22-5b --imagem x.png --prompt "..."` | 7,4 min | Funciona e cabe nos 12GB, 121 quadros a 24fps, mas mais "mole" e o sol estourou e apagou os rostos no meio |
| **14B hi-res fix (padrão p/ `--max-lado` > 832)** | `gerar_video.py --imagem x.png --prompt "..." --max-lado 1280` | **6,4 min** | **Melhor**: movimento gerado em 832 (estável) + refino em 720p com o low noise (re-ruído do passo 2 de 4). Detalhe real e câmera firme |
| 14B nativo 1280x720 (`--nativo`) | `... --max-lado 1280 --nativo` | 7,6 min | Detalhe bom, mas **a câmera treme** com 81 quadros (ver abaixo) |

- **Tremor do 14B nativo em 720p** (medido com phase correlation, tudo reduzido a 832):
  a "aceleração" da câmera quadro a quadro foi 0,5–5,3 nos três vídeos nativos de
  81 quadros, contra 0,07–0,13 nos de 832, no 720p nativo com só 33 quadros e no
  hi-res fix. 8 passos ou shift 8 no nativo não resolvem o problema na raiz. Não é
  a interpolação nem o VAE em pedaços (não houve fallback de memória).
  O hi-res fix também deixou a ação melhor: a flecha do arqueiro sai voando,
  enquanto no nativo ela some.
- **Vertical 720x1280 (Reels/Shorts)** com o 14B nativo também rodou: 7,6 min,
  RAM livre mínima 5,6GB (moça correndo na praia com border collie, imagem 9:16 do Krea2).
- `--upscale LxA` roda uma 2ª passada no ComfyUI (`workflows/upscale_video.json`):
  4x-UltraSharp quadro a quadro e reduz para LxA. Antes disso o script chama
  `/free` para tirar o Wan da RAM.
- Kit do 5B: `setup_models.py --kit wan22-5b -y` (~11GB; o 4x-UltraSharp vem no kit `wan22`).
- O 14B nativo em 720p, que em 2026-10-13 travou o PC, agora rodou liso: o
  ComfyUI atual faz "dynamic VRAM loading" (comfy-aimdo) e o servidor foi
  aberto sozinho, sem o app Desktop/navegador pesando na RAM. O pagefile
  desta máquina é de só 2GB — se a RAM acabar o PC trava em vez de ficar lento,
  então evite usar o PC pesado durante a geração.
- Dica de imagem inicial: gere em 16:9 no Krea2 (`image_gen/`); o 9:16 dele
  tem mais defeitos.

## Vários personagens → vídeo (Qwen-Image 2.1 + Wan 2.2)

Workflow de UI `workflows/ui/Personagens-para-Video-Qwen2.1+Wan2.2.json`,
também copiado para a lista de workflows do ComfyUI (ao lado dos do Qwen).
`workflows/personagens_i2v.json` é o mesmo grafo em formato API.

1. **Referências**: um `LoadImage` por personagem/cenário (image1, image2, image3;
   image4 já ligado mas desativado — Ctrl+B). O `TextEncodeQwenImage21` aceita até
   16; para mais, duplique um `LoadImage` e ligue no próximo `image_N` livre.
2. **Cena**: o Qwen-Image 2.1 (int8 + LoRA Turbo, 8 passos) compõe o 1º quadro
   (768x1376) a partir de um prompt que cita as imagens como `<image1>`, `<image2>`...
   (convenção do próprio Qwen 2.1 para multi-imagem). Seed *fixed*: mudar só o
   prompt do movimento reaproveita a cena.
3. **Vídeo**: o Wan 2.2 anima esse quadro (464x832, 81 frames) com um prompt de
   movimento separado.

Modelos: `setup_models.py --kit personagens -y` (Wan 2.2 + Qwen 2.1; pula o que já existe).
Ainda não testado ponta a ponta (validado só contra o `object_info` do ComfyUI 0.37.2).

## Legado: Sulphur-2 / LTX-2.3 (`--modelo ltx`, kit `--kit ltx`)

> [!WARNING]
> Descontinuado: a qualidade do Sulphur-2 / LTX-2.3 se mostrou insatisfatória em testes práticos. Código mantido para referência.

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
