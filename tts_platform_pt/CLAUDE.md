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
uvicorn server.main:app --reload --port 8011
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
- `scripts/gerar_video.py` — automatiza a produção de áudio a partir de um
  roteiro: sintetiza o texto inteiro (vídeo longo) e, a partir da duração
  medida desse áudio, calcula a taxa de palavras/minuto real daquela voz
  para agrupar as mesmas frases em blocos de ~1 min (vídeo curto), sem
  hardcodar uma taxa de fala fixa. Cliente HTTP do próprio `/api/synthesize`
  — requer o servidor rodando. Ver `Projetos/<nome>/` para convenção de
  pastas de entrada/saída.

## Automação: `scripts/gerar_video.py`

Gera, a partir de um roteiro de texto único, tanto o vídeo longo quanto as
partes curtas para redes sociais, usando o servidor local via HTTP.

```powershell
# com o servidor já rodando (uvicorn server.main:app --port 8011)
.\venv\Scripts\python.exe scripts\gerar_video.py Projetos\video-curto\humanidade.md --voz "Ana Florence"
```

- Saída em `<pasta-do-roteiro>/video-longo/<nome>.wav` (roteiro inteiro) e
  `<pasta-do-roteiro>/video-curto/<nome>_01.wav`, `_02.wav`, ... (blocos de
  ~1 min, configurável com `--minutos-por-parte`), mais um
  `<nome>_manifesto.json` com texto, avisos de normalização e duração de
  cada parte.
- Por padrão `--normalizar` fica desligado (mesmo padrão do checkbox do
  front): a normalização via Ollama é opt-in.
- O corte dos blocos curtos respeita limites de frase (nunca corta uma frase
  ao meio); por isso a duração de cada parte varia um pouco em torno do alvo
  em vez de bater exatamente no minuto.
- Usa `pysbd.Segmenter(language="en", ...)` para achar os limites de frase —
  não é erro de digitação: é o mesmo idioma hardcoded que
  `TTS/utils/synthesizer.py` usa por baixo dos panos pra qualquer idioma
  (pysbd não tem regras próprias de português), então o corte do script
  reflete exatamente onde o motor já corta ao sintetizar.

## Gotchas

- O checkpoint do XTTS-v2 (~1.8GB) baixa do Hugging Face no primeiro uso —
  primeira chamada a `/api/synthesize` (ou `/api/voices`, que já instancia o
  engine) é lenta e precisa de internet.
- `voice_id` no formato `"custom:<arquivo>.wav"` usa clonagem via
  `speaker_wav`; qualquer outro valor é tratado como nome de locutor embutido
  do XTTS-v2 (`speaker=`). Ver `TTSEngine.synthesize` em `tts_engine.py`.
- Sem HTTPS/SSL (diferente do karaoke) — este servidor não captura microfone,
  então não precisa de contexto seguro; HTTP simples em `127.0.0.1:8011` basta.
- **Bug conhecido do XTTS-v2 em português**: o modelo às vezes verbaliza "."
  como a palavra "ponto" em vez de tratá-lo como pausa
  ([coqui-ai/TTS#2952](https://github.com/coqui-ai/TTS/issues/2952), sem fix
  oficial). Mitigado em `tts_engine.py` (`_sanitizar_pontuacao_pt`): troca
  pontos finais por `|` antes de sintetizar em pt (preserva números decimais
  como "3.14"). Só ataca esse bug específico, não é uma correção do modelo.
  **Importante**: a troca só pode acontecer DEPOIS que o texto já foi dividido
  em frases via `self.tts.synthesizer.split_into_sentences(text)` (pysbd, que
  usa o ponto pra achar os limites de frase). Se a troca acontecesse antes da
  divisão, o texto inteiro vira uma única "frase" sem pontos pra dividir, e
  textos longos estouram o limite de 400 tokens do XTTS-v2 (`❗ XTTS can only
  generate text with a maximum of 400 tokens`). Por isso `TTSEngine.synthesize`
  sintetiza frase por frase (`split_sentences=False` por chamada) e concatena
  o áudio manualmente com `numpy`, em vez de passar o texto inteiro pro
  `tts_to_file` de uma vez.
  **Pausas entre frases**: cada frase sintetizada isoladamente já vem com
  silêncio próprio de abertura/fechamento; concatenar sem tratar isso faz o
  silêncio nativo somar com qualquer gap adicionado, ficando artificialmente
  longo e "mudo" (medido: 0.82s, contra ~0.55s de uma pausa natural de "."
  numa única chamada contínua). `_trim_silencio` apara esse silêncio de cada
  clipe (limiar de RMS) antes de somar `_GAP_ENTRE_FRASES_S` (0.35s, ajustado
  empiricamente pra soar próximo do natural).
  **Cuidado ao cortar rente**: aparar exatamente no ponto onde o RMS cruza o
  limiar corta o fim da frase de forma abrupta (soa como a fala foi cortada,
  mesmo sem remover fonemas de fato — o problema é a transição brusca pro
  silêncio, não perda de conteúdo). `_trim_silencio` por isso mantém uma
  margem (`_MARGEM_TRIM_S`, 80ms) além do limiar e aplica um fade-in/fade-out
  curto (`_FADE_S`, 30ms) nas bordas do clipe cortado. Se for mexer nesses
  números, meça com RMS por janela (script usado: gerar o clipe, calcular RMS
  em janelas de 20ms, olhar os valores perto do ponto de corte) em vez de
  julgar de ouvido.
- **XTTS-v2 "trava"/alonga demais em frases com datas compostas** (ex.: "Roma,
  26 de abril de 121 – Vindobona, 17 de março de 180"): uma frase que deveria
  durar ~5s saiu com 14-17s (repetição/alucinação do decoder autoregressivo).
  Isolei a causa testando várias variantes (ver conversa) — **não é parêntese
  nem travessão** (removendo cada um separadamente o problema persistiu) e
  **não é resolvido escrevendo os números por extenso**. O gatilho parece ser
  especificamente **duas expressões "dia de mês de ano" completas na mesma
  frase** (nascimento + morte); com só um número/data por frase (mesmo cru,
  em dígitos) a duração fica normal. Sem correção automática implementada —
  o workaround é reescrever esse tipo de frase biográfica quebrando em duas
  (ex.: "X nasceu em Roma em 26 de abril de 121. Morreu em Vindobona em 17 de
  março de 180."), já que datas compostas desse jeito são raras no uso comum
  da plataforma. Não é bug de uma voz específica — é o texto, reproduz com
  qualquer locutor.
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
