# YouTube Music Playlist Organizer — Plano de Implementação

## Objetivo
Script Python CLI que lê uma playlist do YouTube Music, classifica cada música por gênero via IA local (Ollama), e reorganiza em playlists separadas por gênero — tudo automaticamente.

---

## Stack

| Lib | Responsabilidade |
|---|---|
| **`ytmusicapi`** | Leitura do YouTube Music (metadados limpos: title, artist, album separados) |
| **`google-api-python-client`** | Escrita: criar playlists e adicionar músicas via API oficial |
| **`google-auth` + `google-auth-oauthlib`** | OAuth2 para a YouTube Data API v3 |
| **`ollama`** | Classificação de gênero local (gemma4:e4b), sem custo |
| **`python-dotenv`** | Credenciais |
| **`rich`** | Output no terminal |

### Por que duas libs de acesso ao YouTube?
O YouTube Music **não tem API oficial própria** — ele roda sobre a YouTube Data API v3. O problema é que via API oficial os metadados chegam colados em um único campo `title` (ex: `"Arctic Monkeys - Do I Wanna Know?"`), dificultando a classificação. A `ytmusicapi` acessa a API interna do YT Music via headers de browser e retorna `artist`, `title` e `album` já separados. Porém, ela é não-oficial e suas operações de **escrita são instáveis** — por isso usamos:
- `ytmusicapi` → **leitura** (buscar músicas com metadados ricos)
- YouTube Data API v3 oficial → **escrita** (criar playlists, inserir músicas)

---

## Fluxo Principal

```
1. Autenticar:
   a. ytmusicapi → autenticação via headers do browser (oauth.json) para leitura
   b. OAuth2 Google → token.json para escrita via API oficial
2. Receber ID da playlist fonte como argumento CLI
3. Buscar todas as músicas via ytmusicapi (retorna title, artist, album separados, sem parsear string)
4. Para cada música:
   a. Montar prompt com title e artist já separados
   b. Chamar Ollama localmente
   c. Normalizar resposta (rock, pop, eletrônico, etc.)
5. Agrupar músicas por gênero
6. Para cada gênero (via YouTube Data API v3 oficial):
   a. Buscar se já existe playlist com esse nome na conta
   b. Se não existir, criar via API
   c. Adicionar músicas (evitar duplicatas checando videoId)
7. Exibir relatório final no terminal
```

---

## Estrutura de Arquivos

```
youtube-organizer/
├── main.py              # entrypoint CLI (argparse)
├── auth.py              # OAuth2 Google (escrita) + setup ytmusicapi (leitura)
├── ytmusic_client.py    # leitura via ytmusicapi: get_playlist_items, get_user_playlists
├── youtube_client.py    # escrita via API oficial: create_playlist, add_to_playlist
├── classifier.py        # chama Ollama, normaliza gênero
├── organizer.py         # lógica de agrupamento e deduplicação
├── config.py            # constantes, mapa de normalização de gêneros
├── .env                 # CLIENT_ID, CLIENT_SECRET
├── oauth.json           # credenciais ytmusicapi (gerado no setup)
└── token.json           # token OAuth2 oficial (gerado após primeiro login)
```

---

## Detalhes Críticos para Implementação

### auth.py
- **ytmusicapi**: rodar `ytmusicapi oauth` uma vez no terminal para gerar `oauth.json` interativamente
- **API oficial**: usar `InstalledAppFlow` do `google-auth-oauthlib`; scopes: `youtube.readonly` + `youtube.force-ssl`; salvar/carregar `token.json` com refresh automático

### ytmusic_client.py (leitura)
- Usar `YTMusic("oauth.json")` para autenticar
- `ytm.get_playlist(playlistId, limit=None)` retorna lista com `title`, `artists[].name`, `album.name` já separados — sem necessidade de parsear string
- Playlist especial "Músicas curtidas": ID fixo `"LM"` → usar `ytm.get_liked_songs(limit=None)`
- Tratar caso onde `artists` é lista (pegar o primeiro ou juntar com `, `)

### youtube_client.py (escrita)
- `playlistItems.list` tem limite de 50 itens por página; implementar loop com `nextPageToken`
- Funções: `get_user_playlists()`, `create_playlist(title)`, `add_to_playlist(playlist_id, video_id)`
- Inserções custam 50 unidades de quota cada — usar com parcimônia

### classifier.py
- Chamar Ollama via `ollama.chat()` ou HTTP local (`localhost:11434`)
- Aplicar mapa de normalização após resposta

### config.py — Mapa de normalização de gêneros
```python
GENRE_ALIASES = {
    "hip hop": "rap",
    "hiphop": "rap",
    "hip-hop": "rap",
    "electronic": "eletrônico",
    "electronico": "eletrônico",
    "eletronico": "eletrônico",
    "classical": "clássico",
    "classico": "clássico",
    "country": "country",
    "r&b": "r&b",
    "rhythm and blues": "r&b",
    "forró": "forró",
    "forro": "forró",
    "axé": "axé",
    "axe": "axé",
    "pagode": "pagode",
    "funk": "funk",
    # gênero não identificado
    "unknown": "outros",
    "desconhecido": "outros",
}
```

### organizer.py
- Agrupar lista de músicas classificadas por gênero
- Checar duplicatas por `videoId` antes de inserir em playlist existente

---

## Rate Limits — Atenção

| Recurso | Limite | Custo por operação |
|---|---|---|
| YouTube Data API | 10.000 unidades/dia | insert: 50 unidades |
| YouTube Data API | 10.000 unidades/dia | list: 1 unidade |
| Ollama | sem limite | — |

- Logar total de unidades consumidas ao final
- Adicionar `time.sleep(0.5)` entre chamadas ao Ollama para não saturar

---

## Interface CLI

```bash
python main.py --source-playlist PLxxxxx [--dry-run] [--model gemma4:e4b]
```

| Flag | Descrição |
|---|---|
| `--source-playlist` | ID da playlist fonte (obrigatório) |
| `--dry-run` | Mostra o que faria sem modificar nada |
| `--model` | Modelo Ollama a usar (padrão: `gemma4:e4b`) |

---

## Prompt para o Ollama (classifier.py)

```python
prompt = f"""Você é um classificador de gênero musical.
Responda APENAS com uma palavra em português minúsculo (ex: rock, pop, sertanejo, rap, eletrônico, mpb, clássico, jazz, outros).
Música: "{title}" - Artista: "{artist}"
Gênero:"""
```

---

## Relatório Final no Terminal (rich)

```
╔══════════════════════════════════════╗
║   YouTube Playlist Organizer — Done  ║
╠══════════════════════════════════════╣
║ Músicas processadas : 120            ║
║ Gêneros encontrados : 8              ║
║ Playlists criadas   : 3              ║
║ Playlists atualizadas: 5             ║
║ Unidades API usadas : 850 / 10.000   ║
╠══════════════════════════════════════╣
║ rock         → 34 músicas            ║
║ pop          → 28 músicas            ║
║ rap          → 21 músicas            ║
║ eletrônico   → 15 músicas            ║
║ mpb          → 12 músicas            ║
║ outros       → 10 músicas            ║
╚══════════════════════════════════════╝
```

---

## Setup Inicial

```bash
pip install ytmusicapi google-auth google-auth-oauthlib google-api-python-client ollama python-dotenv rich

# Gerar credenciais ytmusicapi (leitura) — roda uma vez, abre browser
ytmusicapi oauth

# .env
YOUTUBE_CLIENT_ID=seu_client_id
YOUTUBE_CLIENT_SECRET=seu_client_secret
```

Credenciais OAuth2 oficiais (escrita) obtidas em: https://console.cloud.google.com → APIs & Services → Credentials → OAuth 2.0 Client ID (tipo: Desktop App) → ativar YouTube Data API v3.