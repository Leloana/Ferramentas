import re
from core.youtube_client import YouTubeClient
from core.logger import get_logger
from core.config import (
    MUSIC_CATEGORY_ID, PRE_FILTER_BLACKLIST, MAX_READ_TRACKS,
    DISCARD_LIVE, MIN_TRACK_SECONDS, MAX_TRACK_SECONDS, COST_LIST,
)

_ISO8601_DURATION = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')


def _parse_iso8601_duration(duration):
    """Converte 'PT3M21S' (ISO 8601 da Data API) em segundos. 0 se não parsear."""
    if not duration:
        return 0
    m = _ISO8601_DURATION.fullmatch(duration)
    if not m:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds

class YTMusicClient:
    def __init__(self):
        self.logger = get_logger()
        self.logger.info("Usando Google Data API v3 para leitura...")
        # Usamos o YouTubeClient oficial que já está autorizado com token.json
        self.client = YouTubeClient()

    def get_playlist_items(self, playlist_id):
        target_id = 'LL' if playlist_id == 'LM' else playlist_id
        self.logger.info(f"Buscando músicas da playlist: {target_id}")
        
        raw_items = []
        try:
            request = self.client.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=target_id,
                maxResults=50
            )
            
            while request is not None:
                from core.quota_manager import QuotaManager
                QuotaManager.add_usage(COST_LIST)
                response = request.execute()
                raw_items.extend(response.get("items", []))
                request = self.client.youtube.playlistItems().list_next(request, response)
                # Teto opcional de leitura (None = ler a biblioteca inteira)
                if MAX_READ_TRACKS is not None and len(raw_items) >= MAX_READ_TRACKS:
                    raw_items = raw_items[:MAX_READ_TRACKS]
                    break
        except Exception as e:
            self.logger.warning(f"⚠️ Não foi possível ler a playlist {target_id}: {e}")
            return []

        self.logger.info(f"Total bruto recuperado: {len(raw_items)}. Iniciando pré-filtro...")

        # Processamento em lotes de 50 para pegar as categorias
        final_tracks = []
        for i in range(0, len(raw_items), 50):
            batch = raw_items[i:i+50]
            video_ids = [item['contentDetails']['videoId'] for item in batch]
            
            # Busca detalhes dos vídeos (categoria, status de live e duração)
            from core.quota_manager import QuotaManager
            QuotaManager.add_usage(COST_LIST)
            video_details = self.client.youtube.videos().list(
                part="snippet,contentDetails",
                id=",".join(video_ids)
            ).execute()

            # Mapeia o vídeo inteiro por ID (precisamos de snippet + contentDetails)
            details_map = {v['id']: v for v in video_details.get('items', [])}

            for item in batch:
                vid = item['contentDetails']['videoId']
                video = details_map.get(vid, {})
                snippet = video.get('snippet', item['snippet'])
                content_details = video.get('contentDetails', {})

                category_id = snippet.get('categoryId')
                title = snippet.get('title', '').lower()
                duration_s = _parse_iso8601_duration(content_details.get('duration'))
                is_live = snippet.get('liveBroadcastContent', 'none') != 'none'

                # FILTROS DE EXCLUSÃO (Antes da IA) — configurável em core/config.py
                reason = None
                if category_id != MUSIC_CATEGORY_ID:
                    reason = f"categoria {category_id} != Música"
                elif any(word in title for word in PRE_FILTER_BLACKLIST):
                    reason = "título na blacklist"
                elif DISCARD_LIVE and is_live:
                    reason = "transmissão ao vivo"
                elif MIN_TRACK_SECONDS and duration_s and duration_s < MIN_TRACK_SECONDS:
                    reason = f"curta demais ({duration_s}s)"
                elif MAX_TRACK_SECONDS and duration_s and duration_s > MAX_TRACK_SECONDS:
                    reason = f"longa demais ({duration_s}s)"

                if reason is None:
                    # Tenta pegar o nome do artista/canal de ambos os campos possíveis na API
                    artist = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or "Unknown Artist"

                    if artist.endswith(" - Topic"): artist = artist[:-8]

                    # 'liked_at' = data em que a faixa foi ADICIONADA à playlist
                    # (= data da curtida em LL). Vem do playlistItem, NÃO do
                    # videos().list, cujo publishedAt é a data de upload do vídeo.
                    final_tracks.append({
                        'title': snippet.get('title'),
                        'artist': artist,
                        'id': vid,
                        'liked_at': item['snippet'].get('publishedAt')
                    })
                else:
                    self.logger.debug(f"Pré-descartado [{reason}]: {snippet.get('title')}")

        self.logger.info(f"Músicas restantes após pré-filtro: {len(final_tracks)}")
        return final_tracks

    def get_user_playlists(self):
        self.logger.info("Buscando suas playlists existentes...")
        playlists = {}
        request = self.client.youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50
        )
        
        try:
            while request is not None:
                from core.quota_manager import QuotaManager
                QuotaManager.add_usage(COST_LIST)
                response = request.execute()
                for item in response.get("items", []):
                    title = item["snippet"]["title"]
                    playlists[title] = item["id"]
                request = self.client.youtube.playlists().list_next(request, response)
        except Exception as e:
            self.logger.error(f"Erro ao buscar playlists (API Quota?): {e}")
            
        return playlists
