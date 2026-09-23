# Guia de Execução Rápida: Qwen-Image-2.1 na RTX 4070 (12GB)

Este guia reúne os comandos exatos para quando você sentar na máquina e colocar a produção para rodar do início ao fim sem atritos.

O projeto **[Video_11 (Miyamoto Musashi em Ganryujima)](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/Projetos/Video_11/musashi_duelo_ganryujima)** já foi promovido e está com todas as pastas preparadas para as Partes 1 e 2.

---

## Passo 1: Download Automático dos Modelos (1 Comando)

Criamos o script [`scripts/download_qwen_models.py`](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/scripts/download_qwen_models.py) que baixa os pesos oficiais INT8 e os LoRAs direto para o seu ComfyUI com suporte a continuação se a internet oscilar:

```bash
# Se o ComfyUI estiver no caminho padrão:
python scripts/download_qwen_models.py

# Ou informando a pasta explicitamente:
python scripts/download_qwen_models.py --comfy-dir /caminho/para/ComfyUI
```

---

## Passo 2: Iniciar os Servidores Locais

Abra dois terminais:

1. **Terminal 1 (Servidor de Voz XTTS-v2)**:
   ```bash
   uvicorn server.main:app --port 8011
   ```
2. **Terminal 2 (ComfyUI Desktop)**:
   * Abra o aplicativo ComfyUI Desktop ou inicie o script `main.py` do ComfyUI (ele rodará na porta padrão `http://127.0.0.1:8188`).

---

## Passo 3: Produzir em 1 Comando (Método Recomendado)

Criamos o orquestrador [`scripts/executar_projeto.py`](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/scripts/executar_projeto.py) que roda áudio, imagens Qwen e montagem final do vídeo automaticamente:

```bash
# Parte 1: O Duelo de Ganryujima
python3 scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima

# Parte 2: O Golpe do Remo
python3 scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima_parte2
```

*(Consulte [`FLUXO_RECOMENDADO.md`](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/FLUXO_RECOMENDADO.md) na raiz do repositório para a lista de comandos de todos os outros 10 projetos).*

---

## Passo 4: Execução Manual Passo a Passo (Para Testes / Debug)

Caso deseje rodar ou debugar cada etapa isoladamente:

### 4.1. Gerar o Áudio (Narração XTTS-v2)
```bash
python scripts/gerar_video.py Projetos/Video_11/musashi_duelo_ganryujima/texto.md
```
*(Gera o áudio `audio/texto.wav` e o manifesto `texto_manifesto.json` em ~15 segundos)*.

### 4.2. Gerar as Imagens com Qwen-Image-2.1 e Consistência
```bash
python scripts/gerar_imagens.py Projetos/Video_11/musashi_duelo_ganryujima/texto_manifesto.json \
  --workflow comfy/image_qwen_image_2_1_t2i.json \
  --prompts Projetos/Video_11/musashi_duelo_ganryujima/texto_prompts.json \
  --referencia Projetos/Video_11/musashi_duelo_ganryujima/texto_referencia.json \
  --referencia-workflow comfy/image_qwen_image_2_1_i2i.json
```
*(Gera as 9 cenas em 9:16 vertical na pasta `imagens/`, amarrando a consistência das tomadas de Musashi com `<image1>`)*.

### 3.3. Montar o Vídeo Final (.mp4 com Zoom e Legendas Queimadas)
```bash
python scripts/montar_video.py Projetos/Video_11/musashi_duelo_ganryujima/texto_manifesto.json
```
*(Gera `video/texto_9x16.mp4` pronto para postar)*.

### 3.4. Gerar a Capa / Thumbnail
```bash
python scripts/gerar_capa.py Projetos/Video_11/musashi_duelo_ganryujima/texto_manifesto.json \
  --workflow comfy/image_qwen_image_2_1_t2i.json \
  --prompt "A high-budget cinematic anime movie poster of Miyamoto Musashi standing on a storm-swept sea beach at sunrise holding a heavy carved wooden sword, ocean waves crashing, cherry blossoms swirling in the wind, dramatic lighting in the style of Ufotable, full-color single frame animation still" \
  --titulo "O Duelo Lendário de Musashi (Parte 1/2)"
```
*(Gera `capa.png` com o título desenhado em alta resolução)*.

---

## Passo 4: Produzir a Parte 2 (Continuação Direta)

O processo é idêntico para a **Parte 2/2 (O Golpe do Remo)**:

```bash
# 1. Áudio
python scripts/gerar_video.py Projetos/Video_11/musashi_duelo_ganryujima_parte2/texto.md

# 2. Imagens (reutiliza o Musashi da Parte 1 via texto_referencia.json)
python scripts/gerar_imagens.py Projetos/Video_11/musashi_duelo_ganryujima_parte2/texto_manifesto.json \
  --workflow comfy/image_qwen_image_2_1_t2i.json \
  --prompts Projetos/Video_11/musashi_duelo_ganryujima_parte2/texto_prompts.json \
  --referencia Projetos/Video_11/musashi_duelo_ganryujima_parte2/texto_referencia.json \
  --referencia-workflow comfy/image_qwen_image_2_1_i2i.json

# 3. Montagem
python scripts/montar_video.py Projetos/Video_11/musashi_duelo_ganryujima_parte2/texto_manifesto.json

# 4. Capa
python scripts/gerar_capa.py Projetos/Video_11/musashi_duelo_ganryujima_parte2/texto_manifesto.json \
  --workflow comfy/image_qwen_image_2_1_t2i.json \
  --prompt "A high-octane dynamic action anime climax: a samurai in mid-air slashing with a giant nodachi against another warrior deflecting with a heavy carved wooden oar, explosion of water and sand, blinding lightning speed lines, Ufotable animation style, full-color single frame animation still" \
  --titulo "O Golpe Mortal de Musashi (Parte 2/2)"
```
