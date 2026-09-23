# Ferramentas Utilitárias

Este repositório agrupa scripts, automações e ferramentas diversas criadas para facilitar o dia a dia, organizar fluxos de trabalho e resolver problemas específicos de forma automatizada.

## 🛠️ Ferramentas Disponíveis

### 🟢 Ativas

| Ferramenta | Descrição |
| --- | --- |
| [**Plataforma de TTS e Vídeos** (`tts_platform_pt`)](./tts_platform_pt) | Plataforma de síntese de voz em português (XTTS-v2), geração de imagens com consistência de personagem no ComfyUI (Qwen-Image-2.1 INT8) e orquestrador em lote para produção de vídeos curtos verticais (9:16) para TikTok, Reels e Shorts. |
| [**Karaoke AI Premium** (`karaoke`)](./karaoke) | Ecossistema de karaokê local de alta performance com separação de faixas (Demucs), transcrição e alinhamento fonético em tempo real (Whisper GPU + MMS_FA) e microfones via celular (WebSockets). |
| [**YouTube Music Playlist Organizer** (`youtube_music_playlist_organizer`)](./youtube_music_playlist_organizer) | Script CLI em Python que lê playlists do YouTube Music, classifica as músicas por gênero/vibe via IA local (Ollama) e cria playlists organizadas na conta do YouTube. |
| [**DOCX to PDF Converter** (`docx_to_pdf_converter`)](./docx_to_pdf_converter) | Utilitário em Python para conversão em lote ou individual de documentos Microsoft Word (`.docx`) para PDF utilizando automação COM nativa. |
| [**Local Agent** (`local_agent`)](./local_agent) | Esqueleto e guardrails para agentes ReAct rodando 100% locais via Ollama (`qwen3.5:9b`), com sandboxing e orçamento estrito de VRAM para GPUs de 12GB (RTX 4070). |
| [**Image Gen** (`image_gen`)](./image_gen) | Workflows e guias de geração de imagem para ComfyUI (ex: Krea2 turbo t2i). |

### 🔴 Descontinuadas / Arquivadas (Intactas para Referência)

| Ferramenta | Motivo da Descontinuação |
| --- | --- |
| [**Ecossistema Híbrido** (`ecosistema`)](./ecosistema) | Descontinuado: dependia de alterar/remover permissões de sistema no Android que acabavam quebrando tokens NFC e serviços essenciais do celular. |
| [**Agentic CLI** (`wincli`)](./wincli) | Descontinuado: substituído pelo uso do **Antigravity CLI (`agy`)**. |
| [**Video Gen** (`video_gen`)](./video_gen) | Descontinuado / Pausado: a qualidade do modelo LTX-2.3/Sulphur-2 se mostrou insatisfatória em testes práticos. Reavaliar somente quando houver um modelo novo de alta qualidade viável para 12GB de VRAM. |

## 🚀 Como Usar

Cada projeto dentro deste repositório é independente. Para utilizar qualquer um deles:
1. Navegue até a pasta da ferramenta desejada.
2. Leia o arquivo `README.md` presente dentro da respectiva pasta.
3. Siga as instruções específicas de instalação de dependências e configuração.

## ⚠️ Atenção com Credenciais
Atenção especial para scripts que utilizam APIs de terceiros (como o YouTube Data API). Arquivos de credenciais (`.env`, `oauth.json`, `token.json`) **nunca devem ser commitados**. Eles já estão cobertos no `.gitignore` da raiz deste repositório para evitar vazamentos acidentais de chaves.
