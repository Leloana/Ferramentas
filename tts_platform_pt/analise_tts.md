# Análise Comparativa de Modelos de TTS (Foco em PT-BR e Multilíngue)

Este documento avalia o modelo atualmente utilizado na plataforma (**Coqui XTTS-v2**) frente às alternativas de última geração (2024–2026), com ênfase em **Português Brasileiro (PT-BR)**, capacidades **multilíngues**, **clonagem de voz**, **naturalidade de sotaque** e compatibilidade com GPU **Nvidia RTX 4070 (12GB VRAM)**.

---

## 1. O Diagnóstico do Modelo Atual: Coqui XTTS-v2

O XTTS-v2 foi integrado como motor de síntese inicial pelo seu pioneirismo em clonagem de voz *zero-shot* com áudios de referência curtos (6 a 30 segundos). No entanto, o seu uso prático no projeto revelou limitações severas de arquitetura:

| Problema Conhecido | Causa Técnica | Impacto no Projeto |
| :--- | :--- | :--- |
| **Bug do "Ponto" (`.`)** | O fonetizador do XTTS-v2 verbaliza `.` como a palavra falada *"ponto"* em português em vez de aplicar uma pausa. | Exigiu a criação de um regex de sanitização (`_sanitizar_pontuacao_pt`) que troca todo ponto final por `\|` antes da síntese. |
| **Limite Rígido de 400 Tokens** | O modelo autoregressivo falha catastroficamente e alucina em sentenças médias/longas. | Obriga o sistema a fatiar o roteiro frase por frase via `pysbd` e remontar o áudio manualmente via concatenação com silêncios artificiais (`_trim_silencio`, `_GAP_ENTRE_FRASES_S = 0.35s` e `_LEAD_IN_S = 0.15s`). |
| **Inconsistência de Cadência e Duração** | O XTTS-v2 não opera com semente pseudoaleatória (seed) fixa determinística. | Sintetizar o mesmo texto duas vezes gera tempos de áudio diferentes, obrigando reajustes no `montar_video.py`. |
| **Sotaque Gringo / Metalizado** | Dataset de treinamento desbalanceado, predominantemente anglófono. | Certas sílabas e cadências em português soam forçadas, robóticas ou com prosódia estrangeira. |
| **Descontinuação da Coqui AI** | A empresa mantenedora encerrou operações em janeiro de 2024. | O modelo não recebe mais atualizações oficiais ou melhorias de arquitetura. |
| **Consumo de VRAM** | Ocupa cerca de **2.5GB a 3.5GB de VRAM**. | Disputa VRAM com o modelo de imagem (Qwen-Image-2.1) e Ollama na GPU de 12GB. |

---

## 2. Por que o Kokoro-82M Decepciona em Português?

O **Kokoro-82M** é frequentemente citado como uma das grandes inovações de TTS pelo seu tamanho minúsculo (82M parâmetros, ~325MB) e desempenho estelar em **inglês**. No entanto, para **Português Brasileiro (PT-BR)**, a experiência é frustrante e robótica pelas seguintes razões técnicas:

1. **Dependência Crítica de `espeak-ng` (G2P fraco)**:
   - Em inglês, o Kokoro possui mapeamentos e vocabulário afinados manualmente.
   - Em outros idiomas, ele depende do motor de conversão grafema-para-fonema legado `espeak-ng`.
   - O `espeak-ng` para português brasileiro tem dificuldades graves com **vogais nasais** (*ão, ãe, em, en*), ritmo de acentuação tônica e redução vocálica. O som resultante parece um sintetizador arcaico dos anos 2000 lendo um dicionário fonético de forma truncada.
2. **Ausência de Prosódia Emocional Autônoma**:
   - O modelo lê o texto de forma plana e monótona. Ele não infere contexto dramático ou pausas naturais se não houver pontuação excessiva e artificial colocada manualmente pelo usuário.
3. **Sem Clonagem de Voz Arbitrária**:
   - O Kokoro opera apenas com vozes pré-gravadas (ex: `pf_dora`, `pm_alex`), não permitindo enviar um arquivo `.wav` para clonar uma voz de personagem ou dublador.

> [!WARNING]
> **Veredito sobre o Kokoro em PT-BR**: Excelente para assistentes em inglês e leitores de tela em CPU modesta; **completamente inadequado** para narrações cinematográficas em português brasileiro.

---

## 3. Matriz de Avaliação dos Modelos (Grandes Labs e Independentes)

| Modelo / Laboratório | Qualidade em PT-BR | Clonagem Zero-Shot | Multilíngue | Consumo VRAM | Licença / Disponibilidade | Destaque Técnico |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)** *(Alibaba Qwen)* | ⭐⭐⭐⭐ (8.5/10) | ⭐⭐⭐⭐⭐ (3s áudio) | 10 idiomas (Nativo) | 1.5–4.0 GB (`0.6B`/`1.7B`) | **Apache 2.0** (Open-weight) | Mesma equipe do Qwen-Image-2.1; Voice Design via prompt de texto; latência de 97ms. |
| **[Fish Speech](https://github.com/fishaudio/fish-speech)** *(Fish Audio)* | ⭐⭐⭐⭐⭐ (9.6/10) | ⭐⭐⭐⭐⭐ (SOTA) | 80+ idiomas (Cross-lingual) | 4.5–6 GB (FP16) | BSD-3-Clause / Aberto | Zero robótica; entonação humana viva; tags emocionais (`[sussurro]`, `[grito]`). |
| **[Edge-TTS](https://github.com/rany2/edge-tts)** *(Microsoft Neural)* | ⭐⭐⭐⭐⭐ (9.8/10) | ❌ (Vozes fixas) | 70+ idiomas | **0 GB** (Nuvem grátis) | API Gratuita (Uso livre) | Dicção perfeita de estúdio/rádio em PT-BR; timestamps de palavras nativos. |
| **[VibeVoice](https://github.com/microsoft/VibeVoice)** *(Microsoft Research)* | ⭐⭐⭐⭐ (8.2/10) | ⭐⭐⭐⭐ (Boa) | Multilíngue | ~5.0 GB (`1.5B`) | Restrito / Forks | Especialista em áudios longos contínuos (até 90 min) e múltiplos locutores. |
| **[SeamlessM4T v2](https://huggingface.co/facebook/seamless-m4t-v2-large)** *(Meta FAIR)* | ⭐⭐⭐ (7.2/10) | ⭐⭐⭐ (Média) | 100+ idiomas | ~6.0 GB (`2.3B`) | CC-BY-NC 4.0 (Não-comercial) | Tradução e síntese integradas; tom monótono e vocabulário acadêmico. |
| **[F5-TTS (pt-br)](https://github.com/SWivid/F5-TTS)** *(Comunidade)* | ⭐⭐⭐⭐ (8.5/10) | ⭐⭐⭐⭐ (Muito boa) | PT-BR / EN | 4.0–5.5 GB | MIT (Aberto) | Flow Matching DiT: não-autoregressivo; zero alucinações de repetição. |
| **[Chatterbox](https://github.com/resemble-ai/chatterbox)** *(Resemble AI)* | ⭐⭐⭐⭐ (8.0/10) | ⭐⭐⭐⭐ (Boa) | 23 idiomas (modelo pt-BR) | ~4.5 GB | Apache 2.0 | Pacote dedicado para PT-BR com ajuste de sotaque via `cfg_weight`. |
| **[Parler-TTS](https://github.com/huggingface/parler-tts)** *(Hugging Face)* | ⭐⭐ (4.0/10 em PT) | ❌ (Vozes fixas) | Foco em Inglês | ~2.5 GB (`mini`) | **Apache 2.0** | Controle estilístico por texto descritivo; suporte fraco a PT-BR. |
| **[Kokoro-82M](https://github.com/hexgrad/kokoro)** *(hexgrad)* | ⭐⭐ (5.0/10 em PT) | ❌ (Vozes fixas) | 9 idiomas | < 0.4 GB (ou CPU) | **Apache 2.0** | Ultra-leve, mas fonética PT-BR via `espeak-ng` soa robótica e truncada. |
| **XTTS-v2** *(Coqui - Modelo Atual)* | ⭐⭐⭐ (6.8/10) | ⭐⭐⭐⭐ (Boa) | 17 idiomas | ~3.0 GB | CPML (Coqui descontinuada) | Bug do ponto (`.`), limite de 400 tokens, sotaque estrangeiro ocasional. |

---

## 4. Análise Aprofundada dos Candidatos Recomendados

### A. Fish Speech (v1.5) — O Sucessor Ideal para Clonagem e Docudrama
- **Arquitetura**: Dual-AR Transformer (tratando áudio como tokens de linguagem) com vocoder VQ-GAN neural.
- **Por que é superior ao XTTS-v2**:
  - **Não usa G2P legado**: Aprende a fala de ponta a ponta a partir de gravações reais; não verbaliza pontuação nem engasga em palavras complexas.
  - **Cross-Lingual Verdadeiro**: É possível pegar um clipe de voz de 10s de um dublador japonês de anime ou de um ator americano e fazê-lo falar **Português Brasileiro fluente**, conservando o mesmo timbre e a mesma identidade vocal.
  - **Tags Emocionais**: Suporta marcações diretamente no texto, como `[sussurro]`, `[tom solene]`, `[grito]`, `[pausa dramática]`. Para vídeos sobre batalhas históricas (Termópilas, Ganryujima, Constantinopla), isso eleva a produção a outro nível.
- **Operação na RTX 4070 (12GB)**:
  - O modelo 1.5 em FP16 consome ~4.5GB a 6GB de VRAM.
  - Como o pipeline do projeto gera os arquivos de áudio em etapa prévia (`scripts/gerar_video.py`) e só depois gera as imagens (`scripts/gerar_imagens.py`), **não há conflito de concorrência simultânea** de memória com o Qwen-Image-2.1 se o servidor liberar a VRAM ou rodar sequencialmente.

### B. Edge-TTS — A Solução Instantânea para Locução Documental
- **Arquitetura**: Motor de voz neural Azure da Microsoft.
- **Vozes em Destaque**:
  - `pt-BR-AntonioNeural`: Tom maduro, encorpado, austero. É a voz canônica para narrativas de história militar, tragédias e biografias.
  - `pt-BR-FranciscaNeural`: Tom jornalístico, muito claro e expressivo.
- **Vantagens Práticas**:
  - **Alinhador de Legendas Gratuito**: Retorna nativamente os metadados de `WordBoundary` (início e fim exatos de cada palavra pronunciada), eliminando o desvio do `ForcedAligner` do Wav2Vec2.
  - **Zero Consumo de Hardware**: Não consome 1 byte de VRAM, deixando a GPU 100% fria e livre para o ComfyUI.
- **Limitação**: Depende de conexão à internet e não clona vozes a partir de gravações caseiras.

### C. F5-TTS (Flow Matching) — Estabilidade Não-Autoregressiva
- **Arquitetura**: Difusão baseada em *Flow Matching* (sem o loop autoregressivo do XTTS).
- **Vantagens**:
  - Elimina repetições de palavras e gaguejos.
  - Clonagem rápida a partir de 3–8s de áudio.
  - Checkpoints treinados por brasileiros no Hugging Face (`F5-TTS-pt-br`) que corrigem a prosódia nacional.

---

## 5. Modelos Open Source de Grandes Laboratórios (Big Tech Labs)

A corrida pelos modelos de fundação de áudio gerou lançamentos recentes de grande relevância por laboratórios globais:

### A. Alibaba (Equipe Qwen & Tongyi Lab)
*   **Qwen3-TTS (Lançamento: Início de 2026)**:
    *   **Criadores**: Desenvolvido exatamente pela **mesma equipe da Alibaba responsável pelo Qwen-Image-2.1** e pela família Qwen 2.5/3 de LLMs.
    *   **Código & Pesos**: 100% de código aberto sob licença comercial permissiva **Apache 2.0** no [GitHub (QwenLM/Qwen3-TTS)](https://github.com/QwenLM/Qwen3-TTS) e no Hugging Face.
    *   **Tamanhos de Modelo**:
        *   `0.6B`: Focado em máxima eficiência e baixa latência (~1.5GB a 2GB VRAM).
        *   `1.7B`: Modelo de alta fidelidade e riqueza tímbrica (~3.5GB a 4GB VRAM).
    *   **Suporte a Idiomas**: 10 idiomas oficiais, **incluindo Português**, Inglês, Espanhol, Japonês, Coreano, Francês, Alemão, Russo, Italiano e Chinês.
    *   **Diferenciais Únicos**:
        *   *Voice Cloning*: Clona vozes a partir de apenas **3 segundos** de áudio limpo de referência.
        *   *Voice Design via Prompt*: Permite criar uma voz do zero apenas descrevendo suas características em texto (ex: *"Voz masculina grave, rouca, madura de 50 anos, ritmo lento e tom solene de documentário em português"*).
        *   *Baixa Latência*: Primeiro pacote de áudio entregue em ~97ms via arquitetura Dual-Track com o tokenizador `Qwen3-TTS-Tokenizer-12Hz`.
    *   **Situação em PT-BR**: O modelo suporta português nativamente, mas a comunidade avalia que a base de dados em inglês e mandarim ainda é mais madura que o português brasileiro regional.
*   **CosyVoice 2 (Alibaba FunAudioLLM)**:
    *   Outro projeto de peso da Alibaba, especializado em síntese em streaming de alta fidelidade e clonagem *cross-lingual*.

### B. Microsoft Research
*   **VibeVoice (VibeVoice-1.5B)**:
    *   Focado na geração contínua de **áudio de longa duração** (capaz de gerar até 90 minutos de fala e conversação entre até 4 locutores diferentes sem perder a estabilidade ou degradar a cadência).
    *   *Limitação*: Por políticas de IA responsável e mitigação de *deepfakes*, a Microsoft restringiu o acesso aos pesos oficiais de TTS no repositório principal, priorizando os pesos de reconhecimento de fala (ASR) e forks comunitários.
*   **SpeechT5**: Modelo open-source anterior da Microsoft disponível na biblioteca Hugging Face Transformers, porém com arquitetura mais antiga (estilo 2023) e qualidade bem abaixo do padrão atual.
*   **Edge-TTS**: Não é modelo de código aberto tradicional (pesos não públicos), mas sim uma biblioteca que consome a API neural do Azure de forma aberta e sem custo. É atualmente o benchmark de mercado em naturalidade para português.

### C. Meta AI (FAIR)
*   **SeamlessM4T v2 (`facebook/seamless-m4t-v2-large`)**:
    *   Modelo multimodal unificado da Meta para tradução, reconhecimento e síntese de fala em quase 100 idiomas (incluindo PT-BR).
    *   *Limitações*: Licença estritamente para **pesquisa não-comercial** (CC-BY-NC 4.0), modelo pesado (~2.3B de parâmetros) e tom de voz predominantemente documental/neutro, com pouca maleabilidade dramática.
*   **MMS (Massively Multilingual Speech)**:
    *   Cobre mais de 1.400 idiomas. É uma façanha acadêmica de cobertura linguística, mas usa arquitetura tipo VITS clássica, sem a expressividade cinematográfica dos modelos atuais.
*   **Voicebox**: Um dos modelos mais expressivos desenvolvidos pela Meta, mas cujos pesos **nunca foram abertos ao público** por questões de segurança.

### D. Hugging Face
*   **Parler-TTS (`parler-tts/parler-tts-mini-v1`, `parler-tts-large-v1`)**:
    *   Projeto oficial da Hugging Face sob licença **Apache 2.0**.
    *   Pioneiro no controle estilístico por prompt descritivo de texto (*"A male speaker delivers an animated speech in a studio setting"*).
    *   *Limitação*: Foi treinado quase que exclusivamente em língua inglesa. O suporte a português depende de modelos adaptados experimentalmente por terceiros.

---

## 6. Plano de Implementação Sugerido

Para manter a compatibilidade total com os scripts existentes (`gerar_video.py`, `montar_video.py`) sem quebrar nada do fluxo atual:

1. **Adicionar suporte ao Edge-TTS no Servidor FastAPI**:
   - Criar um novo motor opcional em `server/engine/edge_tts_engine.py`.
   - Adicionar uma flag ou seletor de engine em `/api/synthesize` (`engine="edge" | "xtts" | "fish"`).
   - Benefício imediato: Geração de narrativas perfeitas em PT-BR para os novos projetos sem gastar VRAM.
2. **Preparar Adaptador para o Fish Speech 1.5**:
   - Permitir substituição gradual do backend de clonagem (`custom_voices/*.wav`), proporcionando dublagem cross-lingual e expressividade com tags nos roteiros.
3. **Preservar o XTTS-v2 como Fallback**:
   - Manter o código atual intacto como motor padrão de legado para quem já possui vozes clonadas compatíveis.
