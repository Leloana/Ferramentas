# CLAUDE.md

Orientações para o Claude Code ao trabalhar neste subprojeto.

## Visão Geral

Servidor FastAPI local que sintetiza fala em português com **XTTS-v2**
(`coqui/XTTS-v2`, Hugging Face — multilíngue, clonagem de voz zero-shot),
com normalização opcional de texto via **Ollama** local antes da síntese.
Frontend em Vanilla JS (sem build step), no mesmo padrão do `karaoke/`.

Idioma do projeto: **português**. Logs, comentários e mensagens de UI em
PT-BR; nomes de função/classe/variável em inglês — mesmo padrão dos demais
subprojetos do repositório.

## Como Rodar

```powershell
cd tts_platform_pt
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8010
```

Pré-requisitos externos: Ollama aberto com `qwen3:0.6b` baixado (opcional — o
checkbox "Normalizar" no front é o toggle real; desmarcado, o Ollama nunca é
chamado. Marcado sem Ollama disponível, cai em fallback e usa o texto
original); GPU CUDA recomendada (fallback automático para CPU, mais lento).

## Arquitetura

- `server/main.py` — entrypoint FastAPI; insere `server/` no `sys.path` (igual
  ao `karaoke/server/main.py`) para permitir imports diretos por nome de
  módulo (`import config`, `from routes.synthesize import router`).
- `server/config.py` — constantes: paths (`VOICES_DIR`, `OUTPUT_DIR`), porta,
  nome do modelo XTTS-v2, modelo Ollama default.
- `server/state.py` — singleton `get_tts_engine()`, evita recarregar o modelo
  a cada request.
- `server/engine/tts_engine.py` — wrapper do XTTS-v2 (`TTS.api.TTS`). Aceita a
  licença CPML programaticamente (`COQUI_TOS_AGREED=1`). Fallback CUDA → CPU
  automático no carregamento, igual ao `stt_engine.py` do karaoke.
- `server/engine/text_preprocessor.py` — `normalize(texto)` via
  `ollama.generate(..., format="json")`, no mesmo estilo de
  `youtube_music_playlist_organizer/core/classifier.py`. Retorna
  `(texto, aviso)`: `aviso` é `None` em caso de sucesso, ou uma string
  explicando por que a normalização foi pulada/falhou (VRAM insuficiente,
  Ollama fora do ar, JSON inválido) — a síntese nunca deve quebrar por causa
  desse pré-processamento opcional, e o front mostra o aviso quando existe.
  `num_ctx` do Ollama é escolhido dinamicamente por chamada
  (`_pick_num_ctx()`), reservando VRAM pro XTTS-v2; se não sobrar nem o
  mínimo, pula o Ollama de vez (ver Gotchas).
- `server/routes/synthesize.py` — `POST /api/synthesize`.
- `server/routes/voices.py` — `GET/POST /api/voices` (listar/enviar amostra
  de clonagem).
- `server/voices/custom/` — `.wav` de referência enviados pelo usuário
  (gitignored).
- `server/output/` — `.wav` gerados, servidos via `StaticFiles` em `/audio`
  (gitignored).

## Gotchas

- O checkpoint do XTTS-v2 (~1.8GB) baixa do Hugging Face no primeiro uso —
  primeira chamada a `/api/synthesize` (ou `/api/voices`, que já instancia o
  engine) é lenta e precisa de internet.
- `voice_id` no formato `"custom:<arquivo>.wav"` usa clonagem via
  `speaker_wav`; qualquer outro valor é tratado como nome de locutor embutido
  do XTTS-v2 (`speaker=`). Ver `TTSEngine.synthesize` em `tts_engine.py`.
- Sem HTTPS/SSL (diferente do karaoke) — este servidor não captura microfone,
  então não precisa de contexto seguro; HTTP simples em `127.0.0.1:8010` basta.
- **Bug conhecido do XTTS-v2 em português**: o modelo às vezes verbaliza "."
  como a palavra "ponto" em vez de tratá-lo como pausa
  ([coqui-ai/TTS#2952](https://github.com/coqui-ai/TTS/issues/2952), sem fix
  oficial). Mitigado em `tts_engine.py` (`_sanitizar_pontuacao_pt`): troca
  pontos finais por `|` antes de sintetizar em pt (preserva números decimais
  como "3.14"). Só ataca esse bug específico, não é uma correção do modelo.
- **`torch.cuda.mem_get_info()` não é confiável no Windows/WDDM para medir
  VRAM entre processos** — chegou a reportar 11GB livres quando só havia 4GB
  de verdade (o Ollama, rodando em processo separado, não aparece na conta do
  PyTorch). Por isso `text_preprocessor._free_vram_mb()` usa `nvidia-smi`
  via subprocess, não `torch.cuda.mem_get_info()`. Se for medir VRAM em
  outro lugar do código, replique essa abordagem em vez de confiar no torch.
- O toggle "Normalizar" no front (`normalizarEl`) é a fonte da verdade: só
  quando marcado o backend sequer tenta chamar o Ollama. O contador de
  tokens (`#contador-tokens`) só aparece com o toggle marcado, usa
  `ollama_num_ctx` retornado por `/api/voices` como referência, e é uma
  estimativa grosseira (~4 caracteres/token) — não reflete o `num_ctx`
  real escolhido no momento da síntese, que é recalculado a cada chamada.
