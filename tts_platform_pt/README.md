# 🗣️🎬 Plataforma de TTS e Produção Automatizada de Vídeos Curtos

Plataforma de alta performance para síntese de voz em português e produção automatizada de vídeos verticais (9:16) para **TikTok, YouTube Shorts e Instagram Reels**. 

Combina o modelo **XTTS-v2** para narração e clonagem de voz, **Ollama** para normalização textual inteligente, **ComfyUI com Qwen-Image-2.1 (INT8)** para geração de cenas com continuidade visual de personagens, e **FFmpeg** para montagem final com efeito Ken Burns (pan/zoom) e legendas animadas queimadas no vídeo.

Otimizado especificamente para execução local em GPUs com **12GB de VRAM** (ex: NVIDIA RTX 4070).

---

## 🏛️ Arquitetura e Componentes

```
┌─────────────────┐      ┌─────────────────────────┐      ┌─────────────────────┐
│  Texto & Roteiro│ ───► │  Servidor XTTS-v2       │ ───► │  Áudio & Alinhamento│
│  (Projetos/)    │      │  (Normalização Ollama)  │      │  (MMS_FA / Whisper) │
└─────────────────┘      └─────────────────────────┘      └──────────┬──────────┘
                                                                     │
┌─────────────────────────┐      ┌─────────────────────────┐         │
│  Vídeo Final 9:16       │ ◄─── │  Geração Qwen-Image-2.1 │ ◄───────┘
│  (FFmpeg + Legendas)    │      │  (ComfyUI API c/ LoRA)  │
└─────────────────────────┘      └─────────────────────────┘
```

1. **Voz e Narração (`server/`):** Servidor FastAPI que sintetiza fala em português via **XTTS-v2** com suporte a clonagem zero-shot e pré-processador dinâmico de texto via **Ollama** (expande siglas, números e ajusta pontuação para ritmo natural de fala, medindo a VRAM livre via `nvidia-smi` para evitar estouro de memória).
2. **Interface Web (`client/`):** Frontend interativo para testes de voz, síntese pontual e upload de amostras de áudio para clonagem.
3. **Geração Visual (`comfy/`):** Workflows ComfyUI em formato API para **Qwen-Image-2.1** (Text-to-Image, LoRA e Image-to-Image com suporte a token de continuidade visual `<image1>` para manter o mesmo personagem em múltiplos ângulos e cenas).
4. **Orquestrador em Lote (`scripts/executar_projeto.py`):** Automatiza o pipeline de ponta a ponta: sintetiza o áudio da narração, gera o mapa de alinhamento de palavras, submete as cenas para renderização no ComfyUI e monta o vídeo final `.mp4` vertical.
5. **Acervo de Projetos (`Projetos/`):** Estrutura de projetos roteirizados prontos para produção (incluindo o projeto piloto `Video_11` - *Miyamoto Musashi* e 16 projetos históricos em `ideias/`).

---

## 🚀 Guia Rápido de Execução

> 📖 **Para o guia completo passo a passo com a RTX 4070, consulte [`FLUXO_RECOMENDADO.md`](FLUXO_RECOMENDADO.md).**

### 1. Iniciar os Serviços Necessários

* **Terminal 1 — Servidor XTTS-v2:**
  ```powershell
  cd tts_platform_pt
  .\venv\Scripts\Activate.ps1
  uvicorn server.main:app --port 8011
  ```
  *(Acesse `http://127.0.0.1:8011/` se desejar usar a interface web interativa).*

* **Terminal 2 — ComfyUI Desktop ou Core:**
  Abra o ComfyUI na porta padrão `8188` (`http://127.0.0.1:8188`).

### 2. Produzir um Vídeo Completo em 1 Comando

Execute o orquestrador passando a pasta do projeto desejado:

```powershell
python scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima
```

O script cuidará de:
1. Gerar os áudios individuais ou consolidados via XTTS-v2.
2. Calcular o alinhamento fonético temporal de cada palavra para as legendas.
3. Submeter cada prompt ao ComfyUI (utilizando as imagens anteriores como âncora de continuidade do personagem).
4. Renderizar o vídeo vertical final em `Projetos/<projeto>/video/texto_9x16.mp4`.

---

## 📂 Projetos Prontos no Acervo (`Projetos/ideias/`)

O repositório já conta com 16 projetos históricos pré-configurados (duração < 150s, prompts otimizados e consistência visual):

* **Estilo Anime Cinematográfico:**
  * `musashi_duelo_ganryujima` (Partes 1 e 2)
  * `bruxas_da_noite_1942`
  * `batalha_das_termopilas_480ac`
  * `samurai_negro_yasuke_1581`
  * `tomoe_gozen_kurikara_1183`
  * `carga_dos_hussardos_1683`
* **Estilo Realista / Documentário:**
  * `mergulhadores_de_chernobyl_1986`
  * `minutos_finais_titanic_1912`
  * `resgate_de_dunkirk_1940`
  * `abertura_tumba_tutancamon_1922`
  * `voo_de_lindbergh_1927`
  * `julio_cesar_idos_de_marco` (Partes 1 e 2)
  * `queda_de_constantinopla` (Partes 1 e 2)
  * `joana_darc_orleans` (Partes 1 e 2)
  * `stanislav_petrov_1983`
  * `apollo11_pouso_tenso`

---

## 📚 Documentação Técnica Adicional

* **[`FLUXO_RECOMENDADO.md`](FLUXO_RECOMENDADO.md):** Guia oficial de produção na máquina de GPU.
* **[`comfy/analise_qwen_image_2_1.md`](comfy/analise_qwen_image_2_1.md):** Estudo de viabilidade técnica, consumo de VRAM e mapeamento de nós do Qwen-Image-2.1.
* **[`comfy/guia_execucao_qwen.md`](comfy/guia_execucao_qwen.md):** Procedimento de instalação de nós e setup de workflows no ComfyUI.
* **[`plano_continuidade_personagem.md`](plano_continuidade_personagem.md):** Especificação do sistema de continuidade de personagens através do token `<image1>`.
* **[`analise_tts.md`](analise_tts.md):** Estudo comparativo de modelos de TTS modernos (XTTS-v2, F5-TTS, CosyVoice, ChatTTS).

---

## 🛠️ Requisitos de Instalação

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Para o download dos modelos Qwen-Image-2.1 INT8 otimizados:
```powershell
python scripts/download_qwen_models.py
```
