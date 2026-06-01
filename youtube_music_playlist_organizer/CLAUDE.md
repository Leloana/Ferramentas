# CLAUDE.md

Orientações para o Claude Code (claude.ai/code) ao trabalhar neste repositório.

## Visão Geral

CLI em Python que lê uma playlist do YouTube Music do usuário, classifica cada
faixa com uma LLM **local** (Ollama) segundo uma estratégia escolhida
(gênero / vibe / momento / estação), e reorganiza tudo em playlists temáticas na
conta do usuário via YouTube Data API v3. Interface de terminal "cyberpunk" com
`rich` + `questionary`.

Idioma do projeto: **português**. Logs, prompts da LLM, mensagens de UI e nomes
de variáveis são em PT-BR — mantenha esse padrão ao editar.

## Como Rodar

```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS;  .\venv\Scripts\activate no Windows
pip install -r requirements.txt

# Pré-requisitos externos (precisam estar rodando/configurados):
#  1. Ollama aberto com o modelo baixado (default: gemma4:e4b)
#  2. .env com YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET
#  3. token.json — gerado no 1º login OAuth do browser

python main.py                  # menu interativo (assistente)
python main.py --source-playlist <ID> --strategy vibe --dry-run   # modo direto
```

Não há suíte de testes, linter ou CI configurados. Validação é manual via
`--dry-run` (mostra o plano sem tocar na conta).

### Flags relevantes (`main.py`)
`--source-playlist` (`LM` = Músicas Curtidas), `--strategy {genre,vibe,time,season}`,
`--dry-run`, `--model`, `--limit`, `--since DD-MM-AAAA`, `--batch-size` (default 15),
`--max-playlists`, `--force` (ignora bloqueio de cota),
`--auto` (aceita merges da IA e aplica sem perguntar — para execução agendada).

Exemplo periódico (sem teclado): `python main.py --source-playlist LM --strategy vibe --auto`

## Arquitetura

Pipeline orquestrado em `run_organizer()` ([main.py](main.py)):

1. **Ler** faixas via `YTMusicClient.get_playlist_items` ([core/ytmusic_client.py](core/ytmusic_client.py))
2. **Classificar em lote** com Ollama → `MusicClassifier.batch_deep_classify` (retorna `genero_base/sub_genero/vibe` por faixa)
3. **Plano global** → `MusicClassifier.generate_global_strategy` decide grupos e merges (nomes abstratos com emoji em todas as estratégias)
4. **Atribuir faixa→grupo** → `MusicClassifier.assign_to_groups`: a IA coloca cada música num grupo do plano. Fallback por substring só quando a IA não atribui (sem despejo silencioso no `plano[0]`)
5. **Validação** dos merges (`questionary`); com `--auto`, aceita as sugestões da IA
6. **Sincronizar** (criar/atualizar playlists) via `YouTubeClient` ([core/youtube_client.py](core/youtube_client.py)), com rollback em erro

### Módulos `core/`
- `auth.py` — OAuth2 Google (escrita/leitura via API oficial); `token.json` com refresh automático.
- `youtube_client.py` — toda a I/O com a YouTube Data API v3; `@retry_with_backoff` para erros 5xx/429.
- `ytmusic_client.py` — **leitura** das faixas (apesar do nome, usa a API oficial — veja Gotchas).
- `classifier.py` — prompts e parsing do Ollama; em falha de JSON, divide o lote ao meio e retenta.
- `config.py` — modelo default, custos de cota, `API_DAILY_LIMIT`, pré-filtro (`MUSIC_CATEGORY_ID`, `PRE_FILTER_BLACKLIST`) e `MAX_READ_TRACKS`.
- `quota_manager.py` — contabiliza unidades de cota em `quota_usage.json` (reset diário automático).
- `cache.py` — cache de classificação em `.tracks_cache.json` (chave `{id}_{strategy}`).
- `checkpoint_manager.py` — `.sync_checkpoint.json`; evita reenvio de faixas se a sync for interrompida.
- `dataset_manager.py` — `learning_dataset.json`; guarda execuções e notas do usuário para few-shot futuro.
- `json_utils.py` — `safe_load_json` (backup em corrupção) + `atomic_save_json` (escrita atômica via tmpfile).
- `logger.py` — logger `YTOrganizer`, um `.log` por execução em `logs/`.
- `organizer.py` — utilitário legado de agrupamento (pouco usado; lógica real está em `main.py`).

### Persistência (arquivos na raiz, ignorados pelo git)
`token.json` (auth OAuth2), `.tracks_cache.json`, `.sync_checkpoint.json`,
`quota_usage.json`, `learning_dataset.json`.

## Uso periódico (caso de uso principal)

A intenção do app é **organizar as Músicas Curtidas (`LM`) periodicamente**. Isso
é seguro para re-execução:
- Re-inserções são deduplicadas: faixas já presentes na playlist destino são
  puladas (`get_playlist_items` + `CheckpointManager`), então não se gasta cota
  reenviando o que já foi sincronizado.
- A leitura agora cobre a biblioteca **inteira** (sem teto de 500); ajuste
  `MAX_READ_TRACKS` em `config.py` se quiser limitar.
- Cada execução gera um `.log` próprio com timestamp em `logs/`.

## Cota da API (todas as chamadas custam)

Toda chamada à Data API debita cota — inclusive GETs (`*.list` = 1 unidade).
Custos centralizados em `config.py` (`COST_*`); limite diário 10.000.
**Regra:** todo `.execute()` deve ter um `QuotaManager.add_usage(COST_*)` ao lado
(contado **antes** do envio, para superestimar e não estourar o limite). Custos:
`list`=1, `insert`/`create`/`delete`=50. `delete` só ocorre no rollback. A
estimativa pré-voo fica em `check_quota_limit()` / `total_quota_est`; o débito ao
vivo fica no `QuotaManager` (`quota_usage.json`, reset diário). Prefira `--dry-run`.

## Gotchas

- **`LM` no menu lê o `LL` do YouTube**, não a "Liked Music" do app YT Music. A
  Data API oficial não expõe a lista filtrada do YT Music; por isso entra
  vídeo não-musical. Aproximamos a curadoria com o pré-filtro abaixo.
- **Filtro pré-IA** (tudo em `config.py`): faixa só passa se
  `categoryId == MUSIC_CATEGORY_ID` ("10"), título fora de `PRE_FILTER_BLACKLIST`,
  não for live (`DISCARD_LIVE`) e a duração estiver entre `MIN/MAX_TRACK_SECONDS`.
  Para ler a lista exata do YT Music seria preciso `ytmusicapi` (não-oficial) —
  optou-se por não usar.
- **`organizer.py` é legado** — pouco usado; a lógica de agrupamento real está em
  `run_organizer()` no `main.py`.
