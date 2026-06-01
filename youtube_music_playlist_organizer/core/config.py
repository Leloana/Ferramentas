# Modelo do Ollama. "e4b" é a variante de ~4B do gemma3n; o app valida no
# pre-flight se o modelo existe e lista os instalados se não encontrar.
OLLAMA_MODEL_DEFAULT = "gemma3n:e4b"

# Custos de cota da YouTube Data API v3 (unidades por chamada).
# Toda chamada custa cota — inclusive os GETs de leitura (list = 1 unidade).
# Ref.: https://developers.google.com/youtube/v3/determine_quota_cost
COST_LIST = 1                  # qualquer *.list (playlistItems, videos, playlists)
COST_LIST_PLAYLIST_ITEMS = 1   # alias mantido por compatibilidade
COST_INSERT_PLAYLIST_ITEM = 50
COST_CREATE_PLAYLIST = 50
COST_DELETE_PLAYLIST = 50
API_DAILY_LIMIT = 10000

# ─── Pré-filtro de leitura (aplicado ANTES da IA, em ytmusic_client.py) ───
# A lista "curtidas" do YouTube (LL) mistura música com vídeo comum. Como a API
# oficial não expõe a "Liked Music" do app YT Music, aproximamos a curadoria
# deles com a heurística abaixo. Afrouxe/endureça conforme o seu caso.

MUSIC_CATEGORY_ID = "10"  # categoria "Music" da YouTube Data API (sinal mais forte)

# Palavras no título que denunciam conteúdo não-musical (match por substring,
# título em minúsculas). Cuidado ao adicionar termos que apareçam em músicas.
PRE_FILTER_BLACKLIST = [
    "gameplay", "vlog", "tutorial", "aula de", "react", "reaction",
    "trailer", "review", "análise", "analise", "podcast", "entrevista",
    "interview", "documentário", "documentario", "unboxing", "highlights",
    "ao vivo", "(live)", "[live]", "live performance", "explicação", "explicacao",
]

DISCARD_LIVE = True       # descarta transmissões/lives (liveBroadcastContent != "none")

# Faixas de duração plausíveis para uma "música". 0 ou None desativa o limite.
# Padrões generosos: corta clipes muito curtos e vídeos longos (mixes, podcasts,
# DJ sets, álbuns completos). Ajuste se a sua biblioteca tiver muitos sets longos.
MIN_TRACK_SECONDS = 45
MAX_TRACK_SECONDS = 900   # 15 min

# Teto de faixas lidas por execução. None = ler a biblioteca inteira
# (recomendado para organização periódica das Músicas Curtidas, que crescem
# com o tempo). Defina um inteiro apenas se quiser limitar a leitura.
MAX_READ_TRACKS = None
