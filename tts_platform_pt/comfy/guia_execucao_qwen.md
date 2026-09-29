# Guia de Execução Rápida: Qwen-Image-2.1 na RTX 4070 (12GB)

Este guia reúne os comandos exatos para quando você sentar na máquina da 4070
(Windows) e colocar a produção para rodar do início ao fim sem atritos.

O projeto [Video_11 (Miyamoto Musashi)](../Projetos/Video_11) já está com todas as
pastas preparadas para as Partes 1 e 2.

---

## Passo 0: Preparar a máquina (só na 1ª vez / depois de trocar de modelo)

### 0.1. ComfyUI precisa ser >= v0.37

O Qwen-Image-2.1 **não roda em ComfyUI antigo**: a classe `QwenImage21` só existe
em `comfy/supported_models.py` a partir da v0.37, e o formato de peso
`int8_convrot` depende do `comfy-kitchen` novo (capacidade
`dequantize_int8_convrot_weight`). Em v0.26 o modelo nem é reconhecido.

Conferir a versão instalada e atualizar o core do **ComfyUI Desktop** (o app é só
um invólucro de um clone git normal):

```powershell
$C = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
cd $C
git fetch --tags origin
git checkout -B v0.37.2 tags/v0.37.2      # ou a tag estável mais recente
& "$C\.venv\Scripts\python.exe" -m pip install -r requirements.txt --upgrade
```

> ⚠️ **O `pip install -r requirements.txt` troca o PyTorch CUDA por `torch+cpu`.**
> O `requirements.txt` do ComfyUI lista `torch` sem pin nem índice, e no Windows a
> wheel do PyPI é CPU-only — depois do upgrade o ComfyUI sobe sem GPU. Reinstale as
> wheels CUDA logo em seguida (ou reabra o app Desktop, que restaura o pin do
> `manifest.json` sozinho):
>
> ```powershell
> & "$C\.venv\Scripts\python.exe" -m pip install --index-url https://download.pytorch.org/whl/cu130 `
>     "torch==2.10.0+cu130" "torchvision==0.25.0+cu130" "torchaudio==2.11.0+cu130"
> & "$C\.venv\Scripts\python.exe" -c "import torch; print(torch.__version__, torch.cuda.is_available())"
> ```

### 0.2. Onde os modelos realmente moram

No ComfyUI Desktop a pasta `ComfyUI-Installs\...\ComfyUI\models` fica **vazia**: o
app injeta `extra_model_paths` apontando pra pasta compartilhada
`%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models`. É lá que os `.safetensors`
precisam cair.

Pra que o mesmo caminho valha também quando o ComfyUI é iniciado por linha de
comando (sem o app), existe um `extra_model_paths.yaml` na raiz do clone
apontando `base_path` pra `ComfyUI-Shared`.

### 0.3. Download dos pesos (1 comando, ~17GB)

```powershell
python scripts\download_qwen_models.py
# ou, se o ComfyUI estiver fora dos caminhos padrão:
python scripts\download_qwen_models.py --comfy-dir "C:\caminho\para\ComfyUI-Shared"
```

| Arquivo | Tamanho | Destino |
| :--- | ---: | :--- |
| `qwen_image_2.1_int8_convrot.safetensors` | 7,3 GB | `models/diffusion_models/` |
| `qwen3vl_8b_int8_convrot.safetensors` | 9,4 GB | `models/text_encoders/` |
| `qwen_image_2.1_vae_bf16.safetensors` | 0,7 GB | `models/vae/` |
| `Qwen2.1_Anime_consistency.safetensors` | 168 MB | `models/loras/` |
| `qwen-image-modern-anime-lora.safetensors` | 590 MB | `models/loras/` |

*(O LoRA de anime moderno é publicado no HF como `lora.safetensors` — o nome
"bonito" só existe no destino.)*

---

## Passo 1: Iniciar os Serviços Locais

1. **Terminal 1 — Servidor de Voz XTTS-v2**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   uvicorn server.main:app --port 8011
   ```
2. **Terminal 2 — ComfyUI**: abra o app **ComfyUI Desktop** (ele sobe em
   `http://127.0.0.1:8188`). Pra rodar sem GUI:
   ```powershell
   & "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe" `
     "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\main.py" --port 8188
   ```

---

## Passo 2: Produzir em 1 Comando (Método Recomendado)

O orquestrador [`scripts/executar_projeto.py`](../scripts/executar_projeto.py) roda
áudio, imagens Qwen e montagem final do vídeo automaticamente:

```powershell
# Parte 1: O Duelo de Ganryujima
python scripts\executar_projeto.py Projetos\Video_11\musashi_duelo_ganryujima

# Parte 2: O Golpe do Remo (reaproveita o Musashi da Parte 1 via texto_referencia.json)
python scripts\executar_projeto.py Projetos\Video_11\musashi_duelo_ganryujima_parte2
```

*(Consulte [`FLUXO_RECOMENDADO.md`](../FLUXO_RECOMENDADO.md) para a lista de comandos
de todos os outros projetos do acervo.)*

---

## Passo 3: Execução Manual Passo a Passo (Para Testes / Debug)

### 3.1. Gerar o Áudio (Narração XTTS-v2)
```powershell
python scripts\gerar_video.py Projetos\Video_11\musashi_duelo_ganryujima\texto.md
```

### 3.2. Gerar as Imagens com Qwen-Image-2.1 e Consistência
```powershell
python scripts\gerar_imagens.py Projetos\Video_11\musashi_duelo_ganryujima\texto_manifesto.json `
  --workflow comfy\image_qwen_image_2_1_t2i.json `
  --prompts Projetos\Video_11\musashi_duelo_ganryujima\texto_prompts.json `
  --referencia Projetos\Video_11\musashi_duelo_ganryujima\texto_referencia.json `
  --referencia-workflow comfy\image_qwen_image_2_1_i2i.json
```

> A frase-âncora (a que apresenta o personagem) é t2i pura e **não pode aparecer no
> `texto_referencia.json`** — quem entra lá são só as frases que usam `<image1>`, e
> sempre com índice maior que o da âncora.

### 3.3. Montar o Vídeo Final (.mp4 com Zoom e Legendas Queimadas)
```powershell
python scripts\montar_video.py Projetos\Video_11\musashi_duelo_ganryujima\texto_manifesto.json
```

### 3.4. Gerar a Capa / Thumbnail
```powershell
python scripts\gerar_capa.py Projetos\Video_11\musashi_duelo_ganryujima\texto_manifesto.json `
  --workflow comfy\image_qwen_image_2_1_t2i.json `
  --prompt "A high-budget cinematic anime movie poster of Miyamoto Musashi standing on a storm-swept sea beach at sunrise holding a heavy carved wooden sword, ocean waves crashing, cherry blossoms swirling in the wind, dramatic lighting in the style of Ufotable, full-color single frame animation still" `
  --titulo "O Duelo Lendário de Musashi (Parte 1/2)"
```

---

## Desempenho medido nesta máquina (RTX 4070 12GB, 32GB RAM)

| Métrica | Valor |
| :--- | :--- |
| 1ª imagem da sessão (inclui carregar os pesos) | ~27 s |
| Imagens seguintes (1 MP, 9:16, 25 passos, euler/simple, cfg 1.0) | ~15 s |
| Pico de VRAM durante a geração | ~10,4 GB de 12 GB |
| VRAM ocupada pelo ComfyUI ocioso (modelos em cache) | ~9,6 GB |

Os ~10,4 GB de pico deixam pouca folga pro XTTS-v2 na mesma GPU. Antes da etapa de
áudio (ou ao alternar entre os dois), dá pra devolver a VRAM sem fechar o ComfyUI:

```powershell
curl.exe -X POST http://127.0.0.1:8188/free -H "Content-Type: application/json" -d '{\"unload_models\":true,\"free_memory\":true}'
```
*(Medido: 9,6 GB → 1,1 GB em ~3 s.)*
