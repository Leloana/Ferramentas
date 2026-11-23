# longcat_teste: LongCat-Video INT8 na RTX 4070 12 GB

Ferramenta para testar o [LongCat-Video](https://github.com/meituan-longcat/LongCat-Video)
(Meituan, 13,6B parâmetros, licença MIT) gerando **vídeos verticais de 90 segundos**
numa RTX 4070 12 GB com 32 GB de RAM DDR4.

O LongCat foi escolhido para teste porque gera vídeo longo de forma nativa: ele foi
treinado para *continuar* um vídeo a partir dos últimos quadros, então 90 s saem
como uma cena contínua, sem emendas de imagem estática entre clipes.

> **Status (2026-11-23): implementado e testado só em CPU, com modelos minúsculos.
> Nada rodou ainda na GPU nem com os pesos reais.** O roteiro para o primeiro teste
> está em [TESTES_GPU.md](TESTES_GPU.md). Tempos e consumos abaixo são estimativas
> até lá.

## O problema: o modelo não cabe

| Peça | Original (HF) | Aqui |
|---|---|---|
| DiT (13,6B) | 50,6 GiB fp32 (27 GiB em bf16) | **INT8: ~13 GiB**, metade fixa na GPU e metade vindo da RAM bloco a bloco |
| Text encoder UMT5-XXL | 21,2 GiB fp32 | roda **uma vez no início** em INT8 (~7,7 GiB), grava os embeddings e sai |
| VAE (Wan 2.1) | 0,5 GiB | bf16 na GPU |
| LoRA destilação / refino | 2,5 / 3,2 GiB | **fundidas no peso antes de quantizar** (zero custo em runtime) |
| KV cache da condição | ~4,9 GiB | na RAM (o bloco copia o seu pedaço para a GPU na hora) |

O repositório oficial só tem INT8 pronto para o LongCat-Video-Avatar e pede
flash-attn, `torchrun` e uma GPU de 80 GB. Esta ferramenta usa o código oficial
sem modificar os arquivos dele e acrescenta por cima:

1. **Quantização INT8 em streaming** (`lct/quantizar.py`): lê os shards fp32 tensor a
   tensor, quantiza e grava. O pico de RAM fica perto de 2 GiB em vez de 54 GiB.
   O formato e a conta são os do `QuantizedLinear` oficial (INT8 simétrico por canal),
   e o resultado é **bit a bit igual** ao `quantize_model` oficial (testado).
2. **LoRA fundida**: o modo rápido do LongCat (16 passos, sem CFG) é uma LoRA
   (`cfg_step_lora`) e o refino 720p é outra (`refinement_lora`). Em runtime cada uma
   custaria ~1,5 GiB de VRAM. Aqui `W' = W + escala * up @ down` é somado antes de
   quantizar, gerando uma variante INT8 por uso (`dit_distill`, `dit_refino`, `dit_base`).
   Testado contra o `load_lora` + `enable_loras` oficial: mesmo resultado.
3. **Carregamento no device `meta`** (`lct/carregar.py`): a classe oficial do DiT, se
   instanciada normal, aloca 54 GiB em fp32 antes de carregar os pesos. Aqui ela nasce
   vazia e cada shard é encaixado com `assign=True`.
4. **Offload por bloco** (`lct/offload.py`): os 48 blocos do DiT têm ~270 MiB cada em
   INT8. Os N primeiros ficam fixos na GPU (`--blocos-na-gpu`, `auto` calcula pela VRAM
   livre), os outros ficam na RAM num buffer único registrado como pinned
   (`cudaHostRegister`; o `pin_memory()` comum arredondaria cada tensor para potência de 2,
   ~40% a mais de RAM) e sobem um por vez num stream CUDA separado, enquanto o anterior
   calcula.
5. **Atenção via SDPA** (`lct/patches.py`): o código oficial só tem flash-attn 2/3,
   xformers e BSA; sem eles dá erro. No Windows o flash-attn precisa de wheel exata,
   então o padrão é o `scaled_dot_product_attention` do PyTorch (testado contra a conta
   direta, inclusive a cross-attention com texto de tamanho variável). Com flash-attn
   instalado, `--atencao auto` usa ele.
6. **Sem `torch.distributed`**: os demos oficiais exigem `torchrun` (NCCL, que não existe
   no Windows). Com `cp_split_hw=[1,1]` o código oficial já pula as comunicações.
7. **Vídeo longo retomável** (`lct/gerador.py`): cada segmento é salvo ao terminar; se
   cair (ou você fechar), o mesmo comando continua do segmento seguinte.

## Como sai um vídeo de 90 s

```
prompts ──> UMT5 INT8 (1x, cache em disco) ──> sai da memória
                                                   │
imagem opcional ─┐                                 v
                 ├─> segmento 1: t2v ou i2v, 93 quadros 480x832 (6,2 s a 15 fps)
                 │       │ últimos 13 quadros
                 │       v
                 └─> segmentos 2..17: continuação (generate_vc + KV cache), +80 quadros cada
                                   │
                 1373 quadros (91,5 s) ──> concatena ──> ffmpeg: corta em 90 s,
                                                         minterpolate 15->30 fps,
                                                         escala para 720x1280 ──> final.mp4
```

- 480x832 a 15 fps é a saída nativa do estágio 1 do LongCat (bucket 480p vertical).
- Modo **distill** (padrão): 16 passos, CFG 1, LoRA de destilação. Modo **completo**:
  50 passos com CFG 4 (duas passadas por passo), umas 6x mais lento.
- O refino oficial (720p, e 30 fps no modo completo) existe como `--refino`, mas ver
  "Refino 720p" abaixo.

## Instalação (Windows, PowerShell, na máquina da 4070)

```powershell
cd longcat_teste
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install torch==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124
.\venv\Scripts\python.exe -m pip install "triton-windows<3.3"
.\venv\Scripts\python.exe -m pip install -r requirements.txt

.\venv\Scripts\python.exe preparar.py clonar      # código oficial no commit testado (58eb336)
.\venv\Scripts\python.exe preparar.py baixar      # ~78 GiB do Hugging Face (retomável)
.\venv\Scripts\python.exe preparar.py quantizar   # INT8 do modo distill (~13 GiB, lê os 50 GiB fp32)
.\venv\Scripts\python.exe preparar.py checar      # confere tudo
```

No Linux é igual, trocando `.\venv\Scripts\python.exe` por `venv/bin/python`.

Disco: ~78 GiB do original + ~13 GiB por variante INT8. Depois de quantizar, a pasta
`pesos/LongCat-Video/dit` (50,6 GiB) pode ser apagada se não for gerar outra variante.
`$env:LONGCAT_PESOS = "D:\IA\longcat"` muda onde ficam pesos, INT8 e cache de texto.

## Uso

```powershell
# 90 s vertical a partir de um prompt (em inglês rende melhor)
.\venv\Scripts\python.exe gerar.py --saida output\praia --prompt "realistic filming style, vertical video, a woman walks a golden retriever along the beach at sunset, the camera follows from the front, handheld"

# 90 s com o prompt mudando ao longo do vídeo
.\venv\Scripts\python.exe gerar.py --saida output\chuva --roteiro roteiros\exemplo_90s.json

# começando de uma imagem (recorte central 9:16)
.\venv\Scripts\python.exe gerar.py --saida output\foto --imagem minha.png --prompt "..."
```

Para retomar depois de uma queda, rode **o mesmo comando**. Mudou prompt, seed ou modo?
Use outra `--saida` ou `--recomecar`.

### Roteiro

`roteiros/exemplo_90s.json`: lista de trechos com `segundos` e `prompt` (o último sem
`segundos` vai até o fim). Cada segmento de ~5,3 s usa o prompt do trecho em que começa.
Repita personagem, roupa, lugar e câmera em todos os trechos e mude só a ação: o modelo
continua a cena, e um prompt muito diferente tende a gerar corte ou deformação.

### Opções principais

| Opção | Padrão | O que faz |
|---|---|---|
| `--duracao` | 90 | segundos do final.mp4 |
| `--formato` | vertical | `horizontal` gera 832x480 e o final sai 1280x720 |
| `--modo` | distill | `completo` = 50 passos + CFG 4 (lento, precisa de `preparar.py quantizar --variante base`) |
| `--seed` | 42 | cada segmento usa seed + índice |
| `--blocos-na-gpu` | auto | blocos do DiT fixos na GPU; `auto` = (VRAM livre - reserva) / 270 MiB - 2 |
| `--reserva-gib` | 4,5 (distill) | VRAM deixada para ativações no `auto`; calibrar no teste |
| `--atencao` | auto | `sdpa`, `flash2` ou `xformers` |
| `--ffn-tokens` | 16384 | FFN em pedaços (economiza VRAM; 0 desliga) |
| `--texto` | int8-gpu | `bf16-cpu` codifica o prompt exato, sem GPU, mais lento |
| `--kv-cache-gpu` | não | KV cache na GPU (+4,9 GiB de VRAM, menos cópia) |
| `--sem-pin` | não | se o Windows recusar pinned memory grande |
| `--tamanho-final` / `--fps-final` / `--interp` | 720x1280 / 30 / minterpolate | pós no ffmpeg |
| `--quadros` / `--max-segmentos` | 93 / todos | testes curtos |

### O que fica na pasta de saída

| Arquivo | |
|---|---|
| `segmentos/NNN.mp4` | cada segmento assim que termina (dá para assistir durante a geração) |
| `quadros/NNN.npy` | os mesmos quadros sem compressão (o refino lê daqui) |
| `cond.npy` | os 13 quadros que condicionam o próximo segmento |
| `bruto.mp4` | tudo concatenado, 480x832 15 fps |
| `final.mp4` | cortado em 90 s, 30 fps, 720x1280 |
| `estado.json` | progresso e assinatura das opções |
| `medicoes.jsonl` | tempo, pico de VRAM e RAM livre de cada etapa |

## Tempo e memória esperados (estimativa, não medido)

Conta usada: 37,4 mil tokens por segmento em 480x832 (24 quadros latentes x 1560),
~1,7 PFLOP por passada do DiT (metade nas lineares, metade na atenção), 4070 entregando
~40 TFLOPS reais em bf16.

| | Por segmento | 90 s (17 segmentos) |
|---|---|---|
| distill (16 passos, sem CFG) | ~10 a 15 min | **~3 a 4 h** |
| completo (50 passos, CFG) | ~60 a 80 min | ~17 a 23 h |
| refino espacial 720p | ~1 h | ~17 h |

O offload custa pouco: ~7 GiB de blocos por passada a ~20 GB/s em pinned é menos de
0,5 s contra ~40 s de cálculo, e a cópia acontece em paralelo. Sem flash-attn (SDPA)
a parte da atenção deve ficar mais lenta; o `teste_gpu.py` mede as duas.

RAM durante a geração: DiT INT8 ~13 GiB + KV cache ~5 GiB + Python/CUDA ~3 GiB, ~21 GiB.
A máquina da 4070 tem pagefile de 2 GB (ver `video_gen/README.md`): se a RAM acabar o PC
trava em vez de ficar lento. Feche o resto antes de gerar.

## Refino 720p (`--refino`), experimental

O LongCat oficial tem um segundo estágio que sobe para 720p (e 30 fps no modo
`completo`), com LoRA própria e atenção esparsa BSA (kernel triton). Ele está ligado
(`preparar.py quantizar --variante refino` e `--refino espacial`), mas:

- `--refino completo` (720p + 30 fps) passa de 170 mil tokens por segmento: as
  ativações sozinhas passam de 12 GB. **Não deve caber** na 4070.
- `--refino espacial` (720p, 15 fps) tem ~85 mil tokens: no limite, e pela conta
  ~1 h por segmento. Serve para comparar qualidade num trecho curto.
- `--refino-sem-bsa` troca a atenção esparsa pela densa: ~15x mais conta, inviável.

Para os 90 s, o caminho realista é o padrão (480p + minterpolate + lanczos no ffmpeg)
ou passar o `bruto.mp4` pelo upscale/RIFE do `video_gen` (ComfyUI), que já está medido
nesta máquina.

## Testes

Em CPU, sem pesos (precisa do código oficial clonado):

```powershell
.\venv\Scripts\python.exe -m pytest -q tests
```

30 testes, ~6 min. Cobrem: INT8 em streaming igual ao oficial bit a bit; LoRA fundida
igual à LoRA oficial em runtime; erro do INT8 no forward < 5%; UMT5 do transformers
rodando com INT8; SDPA igual à conta direta (self e cross com texto de tamanho variável);
FFN em pedaços igual à inteira; offload dando o mesmo resultado e devolvendo os pesos
para a RAM; conta de segmentos e roteiro; ffmpeg (gravar, concatenar, pós); e **o
pipeline oficial ponta a ponta** com DiT, VAE e scheduler minúsculos: t2v + 2
continuações com KV cache, retomada depois de queda dando o mesmo vídeo, opções
diferentes não se misturam, e o refino espacial (troca para `dit_refino`, 720p vertical
1280x704, condição entre segmentos).

Dois ajustes existem só nos testes, porque a CPU não é a GPU: o VAE calcula em fp32
(conv3d em bf16 na CPU leva 223 s por decodificação) e o `torch_gc` oficial vira no-op
(ele chama `torch.cuda.ipc_collect()`).

Bug que os testes pegaram antes da GPU: o UMT5 do transformers lê `wo.weight.dtype` na
FFN, então quantizar todas as lineares do text encoder (como o `quantize_model` oficial
faria) quebrava no primeiro prompt. A `wo` fica em bf16.

Na GPU: [TESTES_GPU.md](TESTES_GPU.md) e `python teste_gpu.py`.

## Riscos conhecidos (a confirmar na GPU)

- **Qualidade do INT8 no DiT base**: a Meituan só publicou INT8 do Avatar. Pesos INT8
  por canal costumam ser quase iguais ao bf16 em DiT, mas não há como comparar aqui
  (o bf16 não cabe em 32 GB de RAM). Avaliar a olho no teste.
- **UMT5 em INT8**: T5 é sensível a precisão. Se o vídeo ignorar o prompt, gere de novo
  com `--texto bf16-cpu` (o cache é por texto, então apague `pesos/cache_texto/`).
- **Deriva em 90 s**: o LongCat oficial demonstra 1 min (11 continuações). 17 continuações
  em INT8 e modo destilado podem acumular erro de cor/identidade. O `teste_gpu.py`
  gera 16 s antes dos 90 s para olhar isso cedo.
- **triton-windows**: o código oficial importa o triton no topo, mesmo sem refino.
- **Pinned memory de ~7 GiB no Windows** (`cudaHostRegister`): se falhar, o offload segue sem pinned
  (mais lento) e avisa; `--sem-pin` força.

## Arquivos

| | |
|---|---|
| `preparar.py` | clonar, baixar, quantizar, checar |
| `gerar.py` | linha de comando da geração |
| `teste_gpu.py` | escada de testes na GPU com tabela de resultados |
| `lct/` | o código (ver docstring de cada módulo) |
| `roteiros/` | exemplos de roteiro |
| `tests/` | testes em CPU |
| `vendor/`, `pesos/`, `output/`, `trabalho/` | gerados, fora do git |
