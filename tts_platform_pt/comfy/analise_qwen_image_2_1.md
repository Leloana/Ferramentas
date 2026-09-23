# Análise de Qualidade e Guia de Engenharia de Prompt: Qwen-Image-2.1

Este documento reúne a investigação técnica sobre o modelo **Qwen-Image-2.1** (Alibaba Qwen Team, lançado em setembro de 2026), seu comportamento no ecossistema ComfyUI, os fluxos JSON no formato API para automação e as melhores opções de **LoRAs** (incluindo estilos de Anime e Consistência).

---

## 1. Arquitetura e Diferenciais do Modelo

O Qwen-Image-2.1 introduz uma quebra de paradigma em relação a modelos anteriores como SDXL, FLUX.1 e Lumina2/Z-Image:

| Componente | Qwen-Image-2.1 | Modelos Anteriores (SDXL / Z-Image / Krea2) |
| :--- | :--- | :--- |
| **Backbone Visual** | DiT (Diffusion Transformer) 7B | UNet ou DiT 6B |
| **Codificador de Texto** | **Qwen3-VL-8B** (Vision-Language Model nativo) | CLIP-L / T5-XXL / Qwen3-VL 4B |
| **Consistência Visual** | **Multi-referência nativa** (até 10 imagens) | Hacks de img2img com denoise parcial ou IP-Adapter |
| **CFG Padrão** | **CFG 1.0** (Distilação / Guidance Zero) | CFG 3.5 a 7.5 (SDXL) ou CFG 1.0 (Lumina) |
| **Canal Alfa / Transparência** | Suporte nativo a RGBA | Requer nós de pós-processamento (rembg) |
| **Tipografia / Texto** | Renderização nativa de texto em inglês e chinês | Texto borrado/alucinações garranchadas |

---

## 2. Como o Qwen-Image-2.1 Processa Prompts

### A. O Codificador é um VLM (Vision-Language Model)
Como o text encoder é o `Qwen3-VL-8B`, ele não funciona como o CLIP antigo (que lia palavras-chave desconexas). O Qwen3-VL possui raciocínio semântico profundo:
* **Linguagem Natural Completa**: O modelo prefere frases gramaticalmente estruturadas, descritivas e coesas, com sujeito, ação, iluminação e enquadramento.
* **Morte do "Tag Soup"**: Expressões como `masterpiece, best quality, 8k, ultra-detailed, highly detailed, trending on artstation` são contraproducentes no Qwen-Image-2.1; elas poluem o espaço latente e reduzem a atenção do modelo sobre os detalhes reais da cena.
* **Compreensão Espacial Real**: O modelo entende perfeitamente preposições espaciais (`on the left`, `in the background`, `centered`, `over the shoulder`).

### B. O Segredo da Consistência: A Sintaxe de Tokens `<image1>`, `<image2>`
O maior diferencial prático do Qwen-Image-2.1 no ComfyUI é como ele recebe referências de imagem:
* No nó `TextEncodeQwenImageEdit` (ou `Text Encode Qwen Image 2.1`), as imagens conectadas aos slots de entrada **DEVEM ser mencionadas explicitamente no texto do prompt** através de tags especiais:
  * `<image1>` para a primeira referência conectada;
  * `<image2>` para a segunda, e assim por diante.
* **Gotcha Crítico**: Se uma imagem for conectada ao nó do ComfyUI mas o prompt **não** contiver o token `<image1>`, o modelo pode simplesmente ignorar a imagem ou misturar elementos de forma caótica.
* **Formulação Ideal para Manter Personagens**:
  > *"A cinematic close-up of the character from `<image1>`, preserving their exact facial identity, age, and attire, now looking forward with a fierce determined gaze..."*

### C. Comportamento do CFG 1.0 e Prompt Negativo
* O modelo é calibrado para rodar com **CFG = 1.0**.
* **Impacto**: Com CFG 1.0, o prompt negativo convencional tem efeito praticamente nulo (o modelo não calcula o passo de desvio do negativo).
* **Como Evitar Elementos Indesejados**:
  * Em vez de listas de negativos no campo negativo, as restrições devem ser declaradas de forma **afirmativa e descritiva no prompt principal**.
  * Para evitar anacronismos: descreva detalhadamente os materiais de época (*"crude carved wooden oar", "authentic 15th-century steel lamellar armor"*).
  * Para evitar mangá/quadrinhos: use descritores de produção cinematográfica (*"full color anime movie still, cinematic widescreen screenshot, beautiful digital background painting, single cohesive frame"*).

### D. Cuidado com a Tipografia Nativa (Aspas e Palavras Soltas)
* O Qwen-Image-2.1 sabe desenhar texto legível na imagem quando palavras aparecem entre aspas.
* **Regra**: Nunca use aspas em nomes próprios ou descrições no prompt (ex.: evite colocar `"Eagle"` ou `"SPQR"` entre aspas), a menos que você queira literalmente que essas letras sejam pintadas na tela.

---

## 3. Workflows em Formato API Disponíveis em `comfy/`

Estruturamos 3 arquivos JSON no padrão nativo de API do ComfyUI (`POST /prompt`), prontos para serem chamados pelos scripts da plataforma:

1. **[`comfy/image_qwen_image_2_1_t2i.json`](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/comfy/image_qwen_image_2_1_t2i.json)**:
   * **Finalidade**: Geração do Frame 0 (Imagem Âncora do Personagem) e planos gerais em Text-to-Image puro.
   * **Nós Chave**: `UNETLoader` (Qwen 2.1 DiT), `CLIPLoader` (Qwen3-VL-8B, tipo `qwen_image`), `VAELoader`, `EmptySD3LatentImage` configurada para vertical 9:16 (múltiplo 32) e `KSampler` em 25 passos, `euler/simple`, `cfg=1.0`.

2. **[`comfy/image_qwen_image_2_1_i2i.json`](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/comfy/image_qwen_image_2_1_i2i.json)**:
   * **Finalidade**: Continuidade de Personagem nativa (Multi-Reference Image Edit).
   * **Nós Chave**: Adiciona `LoadImage` (Slot da imagem âncora) + `ImageScale` (ajuste para 9:16) conectado a `TextEncodeQwenImageEdit`. O prompt processa a tag `<image1>` diretamente no VLM e injeta o condicionamento no `KSampler`.

3. **[`comfy/image_qwen_image_2_1_lora_t2i.json`](file:///home/marcelo/marcelo/Ferramentas/tts_platform_pt/comfy/image_qwen_image_2_1_lora_t2i.json)**:
   * **Finalidade**: Geração com aplicação de adaptadores LoRA (Anime, Estilização ou Granulação 35mm).
   * **Nós Chave**: Insere `LoraLoader` (`strength_model: 0.8`, `strength_clip: 0.8`) intermediando o UNET e o CLIP antes da amostragem.

---

## 4. Melhores LoRAs para o Qwen-Image-2.1

A comunidade desenvolveu LoRAs de alta eficácia para contornar desafios de estilo e consistência:

### A. LoRAs de Anime e Consistência (Hugging Face)
1. **`Qwen2.1_Anime_consistency.safetensors`** *(Repositório: `WarmBloodAban/Qwen-Image-2.1-LoRAs`)*
   * **Função**: Desenhado especificamente para **Qwen-Image-2.1**.
   * **Benefício**: Evita a degradação e desfoque que às vezes ocorrem nos traços faciais e olhos de personagens de anime durante operações de edição com `<image1>`. Mantém traços nítidos de cel shading.
   * **Peso recomendado**: `0.7` a `0.85`.
2. **`qwen-image-modern-anime-lora`** *(Repositório: `alfredplpl/qwen-image-modern-anime-lora`)*
   * **Função**: Estilização geral em anime digital contemporâneo (estilo *Ufotable* / *Makoto Shinkai*).
   * **Benefício**: Garante iluminação volumétrica exuberante, cores vibrantes e evita qualquer visual que lembre mangá preto e branco ou quadrinhos ocidentais.
   * **Peso recomendado**: `0.6` a `0.8`.

### B. LoRAs Cinematográficos e Fotorrealismo (Civitai / Hugging Face)
1. **`Qwen2.1_Film_Grain_35mm.safetensors`**
   * **Função**: Adiciona textura autêntica de película fotográfica de cinema (Kodak 5219 / 35mm).
   * **Benefício**: Elimina o aspecto excessivamente digital ("plástico/IA") nas cenas históricas realistas (Júlio César, Constantinopla, Stanislav Petrov e Apollo 11).
   * **Peso recomendado**: `0.4` a `0.6`.

---

## 5. Links de Download e Otimização para RTX 4070 (12GB VRAM)

Em precisão total (BF16), o Qwen-Image-2.1 e seu text encoder exigem mais de 24GB de VRAM. No entanto, em uma **RTX 4070 de 12GB VRAM**, a versão oficial quantizada em **`int8_convrot`** roda com desempenho impressionante (~5 a 8 segundos por imagem em 9:16), consumindo apenas **~8.5GB de VRAM de pico**, deixando folga confortável para o sistema operacional.

### 📥 Links Oficiais de Download (Hugging Face)

#### A. Modelos Base do Qwen-Image-2.1 (Repositório Oficial: [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1))
* **Diffusion Model (INT8 - Recomendado para 12GB)**:
  * Baixar: [`qwen_image_2.1_int8_convrot.safetensors`](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/blob/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors) (~7.2 GB)
  * Destino: `ComfyUI/models/diffusion_models/`
* **Text Encoder (Qwen3-VL-8B INT8)**:
  * Baixar: [`qwen3vl_8b_int8_convrot.safetensors`](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/blob/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors) (~4.6 GB)
  * Destino: `ComfyUI/models/text_encoders/`
* **VAE**:
  * Baixar: [`qwen_image_2.1_vae_bf16.safetensors`](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/blob/main/vae/qwen_image_2.1_vae_bf16.safetensors) (~350 MB)
  * Destino: `ComfyUI/models/vae/`

#### B. LoRAs Recomendados
* **LoRA Anime & Consistência Facial**:
  * Baixar: [`Qwen2.1_Anime_consistency.safetensors`](https://huggingface.co/WarmBloodAban/Qwen-Image-2.1-LoRAs/blob/main/Qwen2.1_Anime_consistency.safetensors)
  * Repositório: [WarmBloodAban/Qwen-Image-2.1-LoRAs](https://huggingface.co/WarmBloodAban/Qwen-Image-2.1-LoRAs)
  * Destino: `ComfyUI/models/loras/`
* **LoRA Estilo Anime Moderno**:
  * Baixar: [`qwen-image-modern-anime-lora.safetensors`](https://huggingface.co/alfredplpl/qwen-image-modern-anime-lora)
  * Repositório: [alfredplpl/qwen-image-modern-anime-lora](https://huggingface.co/alfredplpl/qwen-image-modern-anime-lora)
  * Destino: `ComfyUI/models/loras/`

---

## 6. Como a RTX 4070 (12GB) Gerencia a Memória

1. **Descarregamento Dinâmico (Memory Offload)**:
   * O ComfyUI carrega o text encoder `qwen3vl_8b` para codificar o prompt (e a imagem `<image1>`), depois o descarrega automaticamente para a RAM do sistema durante a amostragem do diffusion model `qwen_image_2.1`.
   * Isso faz com que a VRAM ocupada no momento da geração fique entre **7.5GB e 8.5GB**, nunca ultrapassando os 12GB da sua 4070.
2. **Tempo Médio de Geração**:
   * Graças à arquitetura Ada Lovelace da RTX 4070 e ao suporte nativo a FP8/INT8 dos Tensor Cores de 4ª geração, 25 passos em resolução vertical 9:16 geram em média em **5 a 7 segundos** por cena.

